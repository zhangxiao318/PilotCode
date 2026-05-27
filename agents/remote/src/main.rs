use serde::{Deserialize, Serialize};
use std::io::{self, BufRead, Write};

#[derive(Debug, Deserialize)]
struct Request {
    id: u64,
    method: String,
    #[serde(default)]
    params: serde_json::Value,
}

#[derive(Debug, Serialize)]
struct Response {
    id: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[tokio::main]
async fn main() {
    let stdin = io::stdin();
    let mut stdout = io::stdout();

    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };

        if line.trim().is_empty() {
            continue;
        }

        let req: Request = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                let resp = Response {
                    id: 0,
                    result: None,
                    error: Some(format!("parse error: {}", e)),
                };
                let _ = writeln!(stdout, "{}", serde_json::to_string(&resp).unwrap());
                continue;
            }
        };

        let resp = dispatch(req).await;
        let _ = writeln!(stdout, "{}", serde_json::to_string(&resp).unwrap());
        let _ = stdout.flush();
    }
}

async fn dispatch(req: Request) -> Response {
    match req.method.as_str() {
        "ping" => Response {
            id: req.id,
            result: Some(serde_json::json!("pong")),
            error: None,
        },
        "read_file" => handle_read_file(req.id, req.params).await,
        "write_file" => handle_write_file(req.id, req.params).await,
        "exec" => handle_exec(req.id, req.params).await,
        _ => Response {
            id: req.id,
            result: None,
            error: Some(format!("unknown method: {}", req.method)),
        },
    }
}

async fn handle_read_file(id: u64, params: serde_json::Value) -> Response {
    let path = params["path"].as_str().unwrap_or("");
    match tokio::fs::read_to_string(path).await {
        Ok(content) => Response {
            id,
            result: Some(serde_json::json!({ "content": content })),
            error: None,
        },
        Err(e) => Response {
            id,
            result: None,
            error: Some(format!("read_file failed: {}", e)),
        },
    }
}

async fn handle_write_file(id: u64, params: serde_json::Value) -> Response {
    let path = params["path"].as_str().unwrap_or("");
    let content = params["content"].as_str().unwrap_or("");
    match tokio::fs::write(path, content).await {
        Ok(()) => Response {
            id,
            result: Some(serde_json::json!(null)),
            error: None,
        },
        Err(e) => Response {
            id,
            result: None,
            error: Some(format!("write_file failed: {}", e)),
        },
    }
}

async fn handle_exec(id: u64, params: serde_json::Value) -> Response {
    let command = params["command"].as_str().unwrap_or("");
    let cwd = params["cwd"].as_str();

    let mut cmd = tokio::process::Command::new("sh");
    cmd.arg("-c").arg(command);
    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }

    match cmd.output().await {
        Ok(output) => Response {
            id,
            result: Some(serde_json::json!({
                "stdout": String::from_utf8_lossy(&output.stdout),
                "stderr": String::from_utf8_lossy(&output.stderr),
                "code": output.status.code()
            })),
            error: None,
        },
        Err(e) => Response {
            id,
            result: None,
            error: Some(format!("exec failed: {}", e)),
        },
    }
}
