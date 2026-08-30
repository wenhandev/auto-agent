mod oauth_callback;
mod runtime_bridge;
mod runtime_host;
mod runtime_protocol;

use runtime_bridge::{RuntimeConnect, RuntimeIpcPaths, SubscriptionState};

use std::fs::OpenOptions;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, RunEvent,
};

struct RuntimeState {
    /// Embedded Python runtime (worker daemon); internal — UI uses Tauri invoke, not HTTP.
    runtime: Mutex<Option<Child>>,
    cloud: Mutex<Option<Child>>,
}

fn backend_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("backend")
}

fn resolve_python_path() -> String {
    if let Ok(python) = std::env::var("AUTO_AGENT_PYTHON") {
        let path = PathBuf::from(&python);
        if path.is_absolute() {
            return python;
        }
        let from_backend = backend_dir().join(&python);
        if from_backend.is_file() {
            return from_backend.to_string_lossy().into_owned();
        }
        return python;
    }
    let venv_python = backend_dir().join(".venv").join("bin").join("python");
    if venv_python.is_file() {
        return venv_python.to_string_lossy().into_owned();
    }
    "python3".into()
}

fn log_stdio(path: &str) -> Stdio {
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map(Stdio::from)
        .unwrap_or_else(|_| Stdio::null())
}

fn sidecar_exe_name() -> &'static str {
    if cfg!(windows) {
        "auto-agent-worker.exe"
    } else {
        "auto-agent-worker"
    }
}

fn resolve_bundled_binary(stem: &str) -> Option<PathBuf> {
    let triple = env!("TAURI_TARGET_TRIPLE");

    fn pick(binaries: &PathBuf, stem: &str, triple: &str) -> Option<PathBuf> {
        let single = binaries.join(format!("{stem}-{triple}"));
        if single.is_file() {
            return Some(single);
        }
        let onedir = binaries
            .join(format!("runtime-{triple}"))
            .join(sidecar_exe_name());
        onedir.is_file().then_some(onedir)
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(macos_dir) = exe.parent() {
            if let Some(found) = pick(&macos_dir.to_path_buf(), stem, triple) {
                return Some(found);
            }
            if let Some(contents) = macos_dir.parent() {
                let resources = contents.join("Resources");
                if let Some(found) = pick(&resources, stem, triple) {
                    return Some(found);
                }
            }
        }
    }

    pick(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries"),
        stem,
        triple,
    )
}

fn bundled_process_cwd(exe: &PathBuf) -> Option<PathBuf> {
    let parent = exe.parent()?;
    if parent.join("_internal").is_dir() {
        Some(parent.to_path_buf())
    } else {
        None
    }
}

fn spawn_cloud_dev() -> Result<Child, String> {
    let python = resolve_python_path();
    Command::new(&python)
        .args([
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
        ])
        .current_dir(backend_dir())
        .stdout(log_stdio("/tmp/auto-agent-cloud.log"))
        .stderr(log_stdio("/tmp/auto-agent-cloud.log"))
        .spawn()
        .map_err(|e| format!("failed to spawn local cloud ({python} -m uvicorn): {e}"))
}

fn spawn_runtime_dev() -> Result<Child, String> {
    let python = resolve_python_path();
    Command::new(&python)
        .args(["-m", "app.worker.daemon"])
        .current_dir(backend_dir())
        .stdout(log_stdio("/tmp/auto-agent-runtime.log"))
        .stderr(log_stdio("/tmp/auto-agent-runtime.log"))
        .spawn()
        .map_err(|e| format!("failed to spawn runtime ({python} -m app.worker.daemon): {e}"))
}

fn runtime_ipc_socket_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .expect("app data dir")
        .join("runtime-ipc.sock")
}

fn runtime_stream_socket_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .expect("app data dir")
        .join("runtime-stream.sock")
}

fn spawn_runtime_bundled(
    path: &PathBuf,
    ipc_uds: &PathBuf,
    stream_uds: &PathBuf,
) -> Result<Child, String> {
    let mut cmd = Command::new(path);
    if let Some(cwd) = bundled_process_cwd(path) {
        cmd.current_dir(cwd);
    }
    for sock in [ipc_uds, stream_uds] {
        if sock.exists() {
            let _ = std::fs::remove_file(sock);
        }
        if let Some(parent) = sock.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
    }
    cmd.args([
        "desktop-host",
        "--ipc-uds",
        &ipc_uds.to_string_lossy(),
        "--stream-uds",
        &stream_uds.to_string_lossy(),
    ])
    .stdout(log_stdio("/tmp/auto-agent-runtime.log"))
    .stderr(log_stdio("/tmp/auto-agent-runtime.log"))
    .spawn()
    .map_err(|e| format!("failed to spawn bundled runtime ({path:?}): {e}"))
}

fn resolve_runtime_connect(app: &AppHandle) -> RuntimeConnect {
    if cfg!(debug_assertions) {
        RuntimeConnect::Tcp
    } else {
        #[cfg(unix)]
        {
            RuntimeConnect::Ipc(RuntimeIpcPaths {
                rpc: runtime_ipc_socket_path(app),
                stream: runtime_stream_socket_path(app),
            })
        }
        #[cfg(not(unix))]
        {
            RuntimeConnect::Tcp
        }
    }
}

fn spawn_cloud(app: &AppHandle) -> Result<(), String> {
    if !cfg!(debug_assertions) {
        return Ok(());
    }
    let state = app.state::<RuntimeState>();
    let mut guard = state.cloud.lock().map_err(|e| e.to_string())?;
    if guard.is_some() {
        return Ok(());
    }
    *guard = Some(spawn_cloud_dev()?);
    Ok(())
}

fn spawn_runtime(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<RuntimeState>();
    let mut guard = state.runtime.lock().map_err(|e| e.to_string())?;
    if guard.is_some() {
        return Ok(());
    }
    if cfg!(debug_assertions) {
        *guard = Some(spawn_runtime_dev()?);
    } else if let Some(path) = resolve_bundled_binary("auto-agent-runtime") {
        #[cfg(unix)]
        {
            let ipc = runtime_ipc_socket_path(app);
            let stream = runtime_stream_socket_path(app);
            *guard = Some(spawn_runtime_bundled(&path, &ipc, &stream)?);
        }
        #[cfg(not(unix))]
        {
            let _ = path;
        }
    }
    Ok(())
}

fn stop_child(slot: &Mutex<Option<Child>>) {
    if let Ok(mut guard) = slot.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
        }
    }
}

fn stop_runtime(app: &AppHandle) {
    let state = app.state::<RuntimeState>();
    stop_child(&state.runtime);
    stop_child(&state.cloud);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            runtime_bridge::runtime_invoke,
            runtime_bridge::runtime_health,
            runtime_bridge::runtime_stream_url,
            runtime_bridge::runtime_subscribe_run_events,
            runtime_bridge::runtime_subscribe_stream,
            runtime_bridge::runtime_unsubscribe,
        ])
        .manage(SubscriptionState::new())
        .setup(|app| {
            let connect = resolve_runtime_connect(app.handle());
            app.manage(connect);

            oauth_callback::spawn_oauth_callback_server(app.handle().clone());
            if let Err(e) = spawn_cloud(app.handle()) {
                eprintln!("auto-agent: cloud spawn failed (UI will still open): {e}");
            }
            if let Err(e) = spawn_runtime(app.handle()) {
                eprintln!("auto-agent: runtime spawn failed (UI will still open): {e}");
            }

            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let show = MenuItem::with_id(app, "show", "Show Window", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;

            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        stop_runtime(app);
                        app.exit(0);
                    }
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }

            Ok(())
        })
        .manage(RuntimeState {
            runtime: Mutex::new(None),
            cloud: Mutex::new(None),
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_runtime(app);
            }
        });
}
