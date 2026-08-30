//! Framed JSON IPC client for the embedded Python desktop-host (Phase 4B).

use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;

use crate::runtime_protocol::{
    decode_response_frame, encode_frame, RuntimeRequest, RuntimeResponse as ProtocolResponse,
};

#[derive(Clone)]
pub struct RuntimeIpcClient {
    socket_path: PathBuf,
}

impl RuntimeIpcClient {
    pub fn new(socket_path: PathBuf) -> Self {
        Self { socket_path }
    }

    pub fn socket_path(&self) -> &Path {
        &self.socket_path
    }

    pub async fn call(&self, method: &str, params: Value) -> Result<ProtocolResponse, String> {
        let request = RuntimeRequest {
            v: crate::runtime_protocol::PROTOCOL_VERSION,
            id: uuid_string(),
            method: method.to_string(),
            params,
        };
        let frame = encode_frame(&request)?;
        let mut stream = UnixStream::connect(&self.socket_path)
            .await
            .map_err(|e| format!("ipc connect {}: {e}", self.socket_path.display()))?;
        stream
            .write_all(&frame)
            .await
            .map_err(|e| e.to_string())?;
        stream.flush().await.map_err(|e| e.to_string())?;

        let mut header = [0u8; 4];
        stream
            .read_exact(&mut header)
            .await
            .map_err(|e| e.to_string())?;
        let length = u32::from_be_bytes(header) as usize;
        let mut body = vec![0u8; length];
        stream
            .read_exact(&mut body)
            .await
            .map_err(|e| e.to_string())?;
        let mut frame = Vec::with_capacity(4 + length);
        frame.extend_from_slice(&header);
        frame.extend_from_slice(&body);
        decode_response_frame(&frame)
    }
}

fn uuid_string() -> String {
    format!(
        "{:x}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    )
}

/// Map protocol response to HTTP-shaped bridge payload for the WebView layer.
pub fn protocol_to_http(response: ProtocolResponse) -> Result<(u16, String), String> {
    if response.ok {
        let mut result = response.result.unwrap_or(json!({}));
        let status = result
            .get("_http_status")
            .and_then(|v| v.as_u64())
            .unwrap_or(200) as u16;
        if let Some(obj) = result.as_object_mut() {
            obj.remove("_http_status");
        }
        let body = serde_json::to_string(&result).map_err(|e| e.to_string())?;
        return Ok((status, body));
    }
    let err = response
        .error
        .ok_or_else(|| "protocol error missing error body".to_string())?;
    let body = serde_json::json!({ "detail": err.message }).to_string();
    Ok((err.status, body))
}

/// Map REST-style sidecar paths used by the UI to IPC method names + params.
pub fn map_http_to_ipc(
    method: &str,
    path: &str,
    body: Option<&str>,
) -> Result<(String, Value), String> {
    let path = path.trim();
    if !path.starts_with('/') {
        return Err(format!("invalid path: {path}"));
    }
    let segments: Vec<&str> = path.trim_matches('/').split('/').collect();

    match (method.to_uppercase().as_str(), segments.as_slice()) {
        ("GET", ["health"]) => Ok(("health".into(), json!({}))),
        ("GET", ["ready"]) => Ok(("ready".into(), json!({}))),
        ("GET", ["status"]) => Ok(("status".into(), json!({}))),
        ("GET", ["doctor"]) => Ok(("doctor".into(), json!({}))),
        ("POST", ["session"]) => {
            let params: Value = parse_json_body(body)?;
            Ok(("session.save".into(), params))
        }
        ("DELETE", ["session"]) => Ok(("session.clear".into(), json!({}))),
        ("GET", ["settings", "llm"]) => Ok(("settings.llm.get".into(), json!({}))),
        ("PUT", ["settings", "llm"]) => {
            let params: Value = parse_json_body(body)?;
            Ok(("settings.llm.put".into(), params))
        }
        ("GET", ["settings", "computer-use"]) => {
            Ok(("settings.computer_use.get".into(), json!({})))
        }
        ("PUT", ["settings", "computer-use"]) => {
            let params: Value = parse_json_body(body)?;
            Ok(("settings.computer_use.put".into(), params))
        }
        ("GET", ["cloud", "workflows"]) => Ok(("cloud.workflows.list".into(), json!({}))),
        ("GET", ["cloud", "workflows", workflow_id]) => Ok((
            "cloud.workflows.get".into(),
            json!({ "workflow_id": workflow_id }),
        )),
        ("POST", ["cloud", "workflows", workflow_id, "pull"]) => Ok((
            "cloud.workflows.pull".into(),
            json!({ "workflow_id": workflow_id }),
        )),
        ("GET", ["drafts"]) => Ok(("drafts.list".into(), json!({}))),
        ("GET", ["drafts", local_id]) => Ok((
            "drafts.get".into(),
            json!({ "local_id": local_id }),
        )),
        ("POST", ["drafts"]) => {
            let params: Value = parse_json_body(body)?;
            Ok(("drafts.save".into(), params))
        }
        ("POST", ["drafts", local_id, "publish"]) => Ok((
            "drafts.publish".into(),
            json!({ "local_id": local_id }),
        )),
        ("GET", ["publish-queue"]) => Ok(("publish_queue.list".into(), json!({}))),
        ("POST", ["publish-queue", "retry"]) => Ok(("publish_queue.retry".into(), json!({}))),
        ("GET", ["runs"]) => Ok(("runs.list".into(), json!({}))),
        ("POST", ["runs"]) => {
            let params: Value = parse_json_body(body)?;
            Ok(("runs.start".into(), params))
        }
        ("GET", ["runs", run_id]) => Ok(("runs.get".into(), json!({ "run_id": run_id }))),
        ("POST", ["runs", run_id, "abort"]) => Ok((
            "runs.abort".into(),
            json!({ "run_id": run_id }),
        )),
        _ => Err(format!("no IPC mapping for {method} {path}")),
    }
}

fn parse_json_body(body: Option<&str>) -> Result<Value, String> {
    match body {
        None | Some("") => Ok(json!({})),
        Some(raw) => serde_json::from_str(raw).map_err(|e| e.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_health_and_session() {
        let (method, _) = map_http_to_ipc("GET", "/health", None).unwrap();
        assert_eq!(method, "health");
        let (method, params) =
            map_http_to_ipc("POST", "/session", Some(r#"{"cloud_url":"https://x"}"#)).unwrap();
        assert_eq!(method, "session.save");
        assert_eq!(params["cloud_url"], "https://x");
    }

    #[test]
    fn maps_computer_use_settings() {
        let (method, _) = map_http_to_ipc("GET", "/settings/computer-use", None).unwrap();
        assert_eq!(method, "settings.computer_use.get");
        let (method, params) = map_http_to_ipc(
            "PUT",
            "/settings/computer-use",
            Some(r#"{"allow_always":"com.apple.TextEdit"}"#),
        )
        .unwrap();
        assert_eq!(method, "settings.computer_use.put");
        assert_eq!(params["allow_always"], "com.apple.TextEdit");
    }
}
