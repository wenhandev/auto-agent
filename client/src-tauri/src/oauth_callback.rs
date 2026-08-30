use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::thread;

use tauri::{AppHandle, Emitter, Manager};

pub const OAUTH_CALLBACK_PORT: u16 = 8745;

const SUCCESS_HTML: &str = r#"<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Auto Agent</title>
  <style>
    body { font-family: system-ui, sans-serif; text-align: center; padding: 4rem; color: #111; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    p { color: #555; }
  </style>
</head>
<body>
  <h1>Sign-in complete</h1>
  <p>You can close this tab and return to Auto Agent.</p>
</body>
</html>"#;

pub fn spawn_oauth_callback_server(app: AppHandle) {
    thread::spawn(move || {
        let addr = format!("127.0.0.1:{OAUTH_CALLBACK_PORT}");
        let listener = match TcpListener::bind(&addr) {
            Ok(listener) => listener,
            Err(err) => {
                eprintln!("auto-agent: oauth callback server failed to bind {addr}: {err}");
                return;
            }
        };

        for stream in listener.incoming().flatten() {
            if let Err(err) = handle_connection(&app, stream) {
                eprintln!("auto-agent: oauth callback request failed: {err}");
            }
        }
    });
}

fn handle_connection(
    app: &AppHandle,
    mut stream: TcpStream,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut buffer = [0u8; 8192];
    let read = stream.read(&mut buffer)?;
    let request = String::from_utf8_lossy(&buffer[..read]);
    let request_line = request.lines().next().unwrap_or("");
    let path = request_line.split_whitespace().nth(1).unwrap_or("/");

    let (pathname, query) = path.split_once('?').unwrap_or((path, ""));
    if pathname != "/login/oauth/callback" {
        write_response(&mut stream, 404, "Not Found", "Not found")?;
        return Ok(());
    }

    let mut code: Option<String> = None;
    let mut error: Option<String> = None;
    for pair in query.split('&').filter(|part| !part.is_empty()) {
        if let Some((key, value)) = pair.split_once('=') {
            match key {
                "code" => code = Some(decode_component(value)),
                "error" => error = Some(decode_component(value)),
                _ => {}
            }
        }
    }

    let payload = serde_json::json!({
        "code": code,
        "error": error,
    });
    let _ = app.emit("oauth-callback", payload);

    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }

    write_response(&mut stream, 200, "OK", SUCCESS_HTML)?;
    Ok(())
}

fn decode_component(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    let bytes = input.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'+' => {
                out.push(' ');
                index += 1;
            }
            b'%' if index + 2 < bytes.len() => {
                if let Ok(decoded) = u8::from_str_radix(
                    std::str::from_utf8(&bytes[index + 1..index + 3]).unwrap_or(""),
                    16,
                ) {
                    out.push(decoded as char);
                    index += 3;
                } else {
                    out.push('%');
                    index += 1;
                }
            }
            byte => {
                out.push(byte as char);
                index += 1;
            }
        }
    }
    out
}

fn write_response(
    stream: &mut TcpStream,
    status: u16,
    status_text: &str,
    body: &str,
) -> std::io::Result<()> {
    let response = format!(
        "HTTP/1.1 {status} {status_text}\r\n\
         Content-Type: text/html; charset=utf-8\r\n\
         Content-Length: {}\r\n\
         Connection: close\r\n\
         \r\n\
         {body}",
        body.len()
    );
    stream.write_all(response.as_bytes())
}
