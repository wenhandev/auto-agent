//! Monolith bridge: UI → Tauri invoke → embedded runtime.
//! Dev: TCP HTTP 127.0.0.1:3921. Release: framed JSON IPC + stream UDS.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use futures_util::StreamExt;
use http_body_util::{BodyExt, Full};
use hyper::body::Bytes;
use hyper::{Method, Request};
use hyper_util::client::legacy::Client;
use hyperlocal::{UnixClientExt, UnixConnector, Uri};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::Message;
use tokio_util::sync::CancellationToken;

use crate::runtime_host::{map_http_to_ipc, protocol_to_http, RuntimeIpcClient};

pub const RUNTIME_PORT: u16 = 3921;

#[derive(Clone)]
pub struct RuntimeIpcPaths {
    pub rpc: PathBuf,
    pub stream: PathBuf,
}

#[derive(Clone)]
pub enum RuntimeConnect {
    /// Dev: full HTTP API on TCP.
    Tcp,
    /// Release: JSON RPC + separate stream HTTP on Unix sockets.
    #[cfg(unix)]
    Ipc(RuntimeIpcPaths),
}

impl Default for RuntimeConnect {
    fn default() -> Self {
        RuntimeConnect::Tcp
    }
}

impl RuntimeConnect {
    fn http_base(&self) -> String {
        match self {
            RuntimeConnect::Tcp => format!("http://127.0.0.1:{RUNTIME_PORT}"),
            #[cfg(unix)]
            RuntimeConnect::Ipc(_) => String::new(),
        }
    }

    fn stream_socket(&self) -> Option<&Path> {
        match self {
            RuntimeConnect::Tcp => None,
            #[cfg(unix)]
            RuntimeConnect::Ipc(paths) => Some(paths.stream.as_path()),
        }
    }

    fn build_tcp_client(&self) -> Result<reqwest::Client, String> {
        reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(120))
            .build()
            .map_err(|e| e.to_string())
    }

    fn build_uds_client(&self) -> Client<UnixConnector, Full<Bytes>> {
        Client::unix()
    }

    async fn request(
        &self,
        method: &str,
        path: &str,
        headers: Option<&HashMap<String, String>>,
        body: Option<String>,
    ) -> Result<(u16, String), String> {
        match self {
            RuntimeConnect::Tcp => {
                self.request_tcp(method, path, headers, body.as_deref())
                    .await
            }
            #[cfg(unix)]
            RuntimeConnect::Ipc(paths) => {
                self.request_ipc(&paths.rpc, method, path, body.as_deref())
                    .await
            }
        }
    }

    #[cfg(unix)]
    async fn request_ipc(
        &self,
        rpc_socket: &Path,
        method: &str,
        path: &str,
        body: Option<&str>,
    ) -> Result<(u16, String), String> {
        let (ipc_method, params) = map_http_to_ipc(method, path, body)?;
        let client = RuntimeIpcClient::new(rpc_socket.to_path_buf());
        let response = client.call(&ipc_method, params).await?;
        protocol_to_http(response)
    }

    async fn request_tcp(
        &self,
        method: &str,
        path: &str,
        headers: Option<&HashMap<String, String>>,
        body: Option<&str>,
    ) -> Result<(u16, String), String> {
        let client = self.build_tcp_client()?;
        let url = format!("{}{}", self.http_base(), path);

        let mut req = match method.to_uppercase().as_str() {
            "GET" => client.get(&url),
            "POST" => client.post(&url),
            "PUT" => client.put(&url),
            "PATCH" => client.patch(&url),
            "DELETE" => client.delete(&url),
            other => return Err(format!("unsupported HTTP method: {other}")),
        };

        if let Some(headers) = headers {
            for (key, value) in headers {
                req = req.header(key, value);
            }
        }
        if let Some(body) = body {
            req = req.body(body.to_string());
        }

        let response = req.send().await.map_err(|e| e.to_string())?;
        let status = response.status().as_u16();
        let body = response.text().await.map_err(|e| e.to_string())?;
        Ok((status, body))
    }

    #[cfg(unix)]
    #[allow(dead_code)]
    async fn request_stream_uds(
        &self,
        method: &str,
        path: &str,
        headers: Option<&HashMap<String, String>>,
        body: Option<String>,
    ) -> Result<(u16, String), String> {
        let socket_path = self
            .stream_socket()
            .ok_or_else(|| "stream socket not configured".to_string())?;
        let client = self.build_uds_client();
        let uri: hyper::Uri = Uri::new(socket_path, path).into();
        let http_method = Method::from_bytes(method.as_bytes())
            .map_err(|e| format!("unsupported HTTP method: {e}"))?;
        let request_body = Full::new(Bytes::from(body.unwrap_or_default()));

        let mut builder = Request::builder().method(http_method).uri(uri);
        if let Some(headers) = headers {
            for (key, value) in headers {
                builder = builder.header(key.as_str(), value.as_str());
            }
        }
        let request = builder
            .body(request_body)
            .map_err(|e| e.to_string())?;

        let response = client.request(request).await.map_err(|e| e.to_string())?;
        let status = response.status().as_u16();
        let collected = response.collect().await.map_err(|e| e.to_string())?;
        let body = String::from_utf8_lossy(&collected.to_bytes()).into_owned();
        Ok((status, body))
    }
}

pub struct SubscriptionState {
    next_id: AtomicU64,
    tokens: Mutex<HashMap<u64, CancellationToken>>,
}

impl SubscriptionState {
    pub fn new() -> Self {
        Self {
            next_id: AtomicU64::new(1),
            tokens: Mutex::new(HashMap::new()),
        }
    }

    fn register(&self) -> (u64, CancellationToken) {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let token = CancellationToken::new();
        self.tokens
            .lock()
            .expect("subscription lock")
            .insert(id, token.clone());
        (id, token)
    }

    fn cancel(&self, id: u64) {
        if let Some(token) = self.tokens.lock().expect("subscription lock").remove(&id) {
            token.cancel();
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct RuntimeRequest {
    pub method: String,
    pub path: String,
    pub body: Option<String>,
    pub headers: Option<HashMap<String, String>>,
}

#[derive(Debug, Serialize)]
pub struct RuntimeResponse {
    pub status: u16,
    pub body: String,
}

#[derive(Debug, Serialize)]
pub struct RuntimeHealth {
    pub runtime_ready: bool,
}

#[derive(Clone, Serialize)]
struct RunEventPayload {
    run_id: String,
    data: String,
}

#[tauri::command]
pub async fn runtime_invoke(
    connect: State<'_, RuntimeConnect>,
    request: RuntimeRequest,
) -> Result<RuntimeResponse, String> {
    let path = if request.path.starts_with('/') {
        request.path.clone()
    } else {
        format!("/{}", request.path)
    };

    let (status, body) = connect
        .inner()
        .request(
            &request.method,
            &path,
            request.headers.as_ref(),
            request.body,
        )
        .await?;

    Ok(RuntimeResponse { status, body })
}

#[tauri::command]
pub async fn runtime_health(connect: State<'_, RuntimeConnect>) -> Result<RuntimeHealth, String> {
    let (status, body) = match connect
        .inner()
        .request("GET", "/health", None, None)
        .await
    {
        Ok(result) => result,
        Err(_) => return Ok(RuntimeHealth { runtime_ready: false }),
    };

    if status != 200 {
        return Ok(RuntimeHealth { runtime_ready: false });
    }

    let Ok(json) = serde_json::from_str::<serde_json::Value>(&body) else {
        return Ok(RuntimeHealth { runtime_ready: false });
    };
    Ok(RuntimeHealth {
        runtime_ready: json.get("status").and_then(|v| v.as_str()) == Some("ok"),
    })
}

#[tauri::command]
pub async fn runtime_subscribe_run_events(
    app: AppHandle,
    connect: State<'_, RuntimeConnect>,
    subs: State<'_, SubscriptionState>,
    run_id: String,
) -> Result<u64, String> {
    let (id, token) = subs.register();
    let connect = connect.inner().clone();
    tokio::spawn(async move {
        if let Err(err) = relay_run_events(app, connect, run_id, token).await {
            eprintln!("auto-agent: run event relay ended: {err}");
        }
    });
    Ok(id)
}

#[tauri::command]
pub async fn runtime_subscribe_stream(
    app: AppHandle,
    connect: State<'_, RuntimeConnect>,
    subs: State<'_, SubscriptionState>,
    run_id: String,
) -> Result<u64, String> {
    let (id, token) = subs.register();
    let connect = connect.inner().clone();
    tokio::spawn(async move {
        if let Err(err) = relay_stream(app, connect, run_id, token).await {
            eprintln!("auto-agent: stream relay ended: {err}");
        }
    });
    Ok(id)
}

#[tauri::command]
pub async fn runtime_unsubscribe(
    subs: State<'_, SubscriptionState>,
    subscription_id: u64,
) -> Result<(), String> {
    subs.cancel(subscription_id);
    Ok(())
}

async fn relay_run_events(
    app: AppHandle,
    connect: RuntimeConnect,
    run_id: String,
    token: CancellationToken,
) -> Result<(), String> {
    let path = format!(
        "/runs/{}/events",
        urlencoding::encode(&run_id)
    );

    match &connect {
        RuntimeConnect::Tcp => relay_run_events_tcp(app, connect, run_id, token, path).await,
        #[cfg(unix)]
        RuntimeConnect::Ipc(_) => {
            relay_run_events_stream_uds(app, connect, run_id, token, path).await
        }
    }
}

async fn relay_run_events_tcp(
    app: AppHandle,
    connect: RuntimeConnect,
    run_id: String,
    token: CancellationToken,
    path: String,
) -> Result<(), String> {
    let client = connect.build_tcp_client()?;
    let url = format!("{}{}", connect.http_base(), path);
    let response = client.get(url).send().await.map_err(|e| e.to_string())?;
    if !response.status().is_success() {
        return Err(format!("SSE connect failed: {}", response.status()));
    }

    let mut stream = response.bytes_stream();
    let mut buffer = String::new();

    while !token.is_cancelled() {
        let chunk = tokio::select! {
            _ = token.cancelled() => break,
            next = stream.next() => next,
        };
        let Some(chunk) = chunk else { break };
        let chunk = chunk.map_err(|e| e.to_string())?;
        buffer.push_str(&String::from_utf8_lossy(&chunk));

        while let Some(pos) = buffer.find("\n\n") {
            let block = buffer[..pos].to_string();
            buffer = buffer[pos + 2..].to_string();
            emit_sse_block(&app, &run_id, &block);
        }
    }
    Ok(())
}

#[cfg(unix)]
async fn relay_run_events_stream_uds(
    app: AppHandle,
    connect: RuntimeConnect,
    run_id: String,
    token: CancellationToken,
    path: String,
) -> Result<(), String> {
    let socket_path = connect
        .stream_socket()
        .ok_or_else(|| "stream socket not configured".to_string())?
        .to_path_buf();
    let client = Client::unix();
    let uri: hyper::Uri = Uri::new(&socket_path, &path).into();
    let request = Request::builder()
        .method("GET")
        .uri(uri)
        .body(Full::new(Bytes::new()))
        .map_err(|e| e.to_string())?;

    let mut response = client.request(request).await.map_err(|e| e.to_string())?;
    if !response.status().is_success() {
        return Err(format!("SSE connect failed: {}", response.status()));
    }

    let mut buffer = String::new();
    while !token.is_cancelled() {
        let chunk = tokio::select! {
            _ = token.cancelled() => break,
            next = response.frame() => next,
        };
        let Some(chunk) = chunk else { break };
        let frame = chunk.map_err(|e| e.to_string())?;
        if let Some(segment) = frame.data_ref() {
            buffer.push_str(&String::from_utf8_lossy(segment));

            while let Some(pos) = buffer.find("\n\n") {
                let block = buffer[..pos].to_string();
                buffer = buffer[pos + 2..].to_string();
                emit_sse_block(&app, &run_id, &block);
            }
        }
    }
    Ok(())
}

fn emit_sse_block(app: &AppHandle, run_id: &str, block: &str) {
    for line in block.lines() {
        if let Some(data) = line.strip_prefix("data: ") {
            let _ = app.emit(
                "runtime-run-event",
                RunEventPayload {
                    run_id: run_id.to_string(),
                    data: data.to_string(),
                },
            );
        }
    }
}

async fn relay_stream(
    app: AppHandle,
    connect: RuntimeConnect,
    run_id: String,
    token: CancellationToken,
) -> Result<(), String> {
    let path = format!("/ws/stream/{}", urlencoding::encode(&run_id));

    match &connect {
        RuntimeConnect::Tcp => {
            let url = format!("ws://127.0.0.1:{RUNTIME_PORT}{path}");
            let (mut ws, _) = tokio_tungstenite::connect_async(url)
                .await
                .map_err(|e| e.to_string())?;
            relay_ws_messages(app, &mut ws, run_id, token).await
        }
        #[cfg(unix)]
        RuntimeConnect::Ipc(_) => {
            let socket_path = connect
                .stream_socket()
                .ok_or_else(|| "stream socket not configured".to_string())?;
            let stream = tokio::net::UnixStream::connect(socket_path)
                .await
                .map_err(|e| e.to_string())?;
            let url = format!("ws://localhost{path}");
            let request = url
                .as_str()
                .into_client_request()
                .map_err(|e| e.to_string())?;
            let (mut ws, _) = tokio_tungstenite::client_async(request, stream)
                .await
                .map_err(|e| e.to_string())?;
            relay_ws_messages(app, &mut ws, run_id, token).await
        }
    }
}

async fn relay_ws_messages<S>(
    app: AppHandle,
    ws: &mut tokio_tungstenite::WebSocketStream<S>,
    run_id: String,
    token: CancellationToken,
) -> Result<(), String>
where
    S: tokio::io::AsyncRead + tokio::io::AsyncWrite + Unpin,
{
    while !token.is_cancelled() {
        let msg = tokio::select! {
            _ = token.cancelled() => break,
            next = ws.next() => next,
        };
        let Some(msg) = msg else { break };
        match msg.map_err(|e| e.to_string())? {
            Message::Text(text) => {
                let payload: serde_json::Value = serde_json::from_str(&text)
                    .unwrap_or(serde_json::json!({ "raw": text.to_string() }));
                let _ = app.emit(
                    "runtime-stream-frame",
                    serde_json::json!({ "run_id": run_id, "payload": payload }),
                );
            }
            Message::Close(_) => break,
            _ => {}
        }
    }

    let _ = ws.close(None).await;
    Ok(())
}

/// Dev-only: expose internal stream URL for browser testing without Tauri relay.
#[tauri::command]
pub fn runtime_stream_url(connect: State<'_, RuntimeConnect>, path: String) -> String {
    let path = if path.starts_with('/') {
        path
    } else {
        format!("/{path}")
    };
    match connect.inner() {
        RuntimeConnect::Tcp => format!("{}{}", connect.inner().http_base(), path),
        #[cfg(unix)]
        RuntimeConnect::Ipc(_) => format!("http://localhost{path}"),
    }
}
