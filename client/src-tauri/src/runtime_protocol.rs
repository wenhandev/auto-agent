//! Structured message protocol for desktop runtime IPC (Phase 4B).
//! Frame: 4-byte big-endian length + UTF-8 JSON body.

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const PROTOCOL_VERSION: u32 = 1;
pub const MAX_FRAME_BYTES: usize = 16 * 1024 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeErrorBody {
    pub code: String,
    pub message: String,
    #[serde(default = "default_error_status")]
    pub status: u16,
}

fn default_error_status() -> u16 {
    400
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeRequest {
    #[serde(default = "default_version")]
    pub v: u32,
    pub id: String,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeResponse {
    #[serde(default = "default_version")]
    pub v: u32,
    pub id: String,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<RuntimeErrorBody>,
}

fn default_version() -> u32 {
    PROTOCOL_VERSION
}

pub fn encode_frame(value: &impl Serialize) -> Result<Vec<u8>, String> {
    let body = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    if body.len() > MAX_FRAME_BYTES {
        return Err("frame too large".into());
    }
    let mut frame = Vec::with_capacity(4 + body.len());
    frame.extend_from_slice(&(body.len() as u32).to_be_bytes());
    frame.extend_from_slice(&body);
    Ok(frame)
}

pub fn decode_request_frame(data: &[u8]) -> Result<RuntimeRequest, String> {
    let body = frame_body(data)?;
    serde_json::from_slice(&body).map_err(|e| e.to_string())
}

pub fn decode_response_frame(data: &[u8]) -> Result<RuntimeResponse, String> {
    let body = frame_body(data)?;
    serde_json::from_slice(&body).map_err(|e| e.to_string())
}

fn frame_body(data: &[u8]) -> Result<Vec<u8>, String> {
    if data.len() < 4 {
        return Err("frame too short".into());
    }
    let length = u32::from_be_bytes([data[0], data[1], data[2], data[3]]) as usize;
    if length > MAX_FRAME_BYTES {
        return Err("frame length exceeds limit".into());
    }
    if data.len() < 4 + length {
        return Err("incomplete frame".into());
    }
    Ok(data[4..4 + length].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_request_frame() {
        let req = RuntimeRequest {
            v: PROTOCOL_VERSION,
            id: "abc".into(),
            method: "health".into(),
            params: Value::Object(Default::default()),
        };
        let frame = encode_frame(&req).expect("encode");
        let decoded = decode_request_frame(&frame).expect("decode");
        assert_eq!(decoded.id, "abc");
        assert_eq!(decoded.method, "health");
    }

    #[test]
    fn round_trip_response_frame() {
        let res = RuntimeResponse {
            v: PROTOCOL_VERSION,
            id: "abc".into(),
            ok: true,
            result: Some(serde_json::json!({"status": "ok"})),
            error: None,
        };
        let frame = encode_frame(&res).expect("encode");
        let decoded = decode_response_frame(&frame).expect("decode");
        assert!(decoded.ok);
    }
}
