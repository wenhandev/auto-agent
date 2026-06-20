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
    sidecar: Mutex<Option<Child>>,
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
    let triple = option_env!("TARGET").unwrap_or("unknown");
    let binaries = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries");

    let single = binaries.join(format!("{stem}-{triple}"));
    if single.is_file() {
        return Some(single);
    }

    let onedir = binaries
        .join(format!("runtime-{triple}"))
        .join(sidecar_exe_name());
    onedir.is_file().then_some(onedir)
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

fn spawn_cloud_bundled(path: &PathBuf) -> Result<Child, String> {
    let mut cmd = Command::new(path);
    if let Some(cwd) = bundled_process_cwd(path) {
        cmd.current_dir(cwd);
    }
    cmd.stdout(log_stdio("/tmp/auto-agent-cloud.log"))
        .stderr(log_stdio("/tmp/auto-agent-cloud.log"))
        .spawn()
        .map_err(|e| format!("failed to spawn bundled local cloud ({path:?}): {e}"))
}

fn spawn_sidecar_dev() -> Result<Child, String> {
    let python = resolve_python_path();
    Command::new(&python)
        .args(["-m", "app.worker.daemon"])
        .current_dir(backend_dir())
        .stdout(log_stdio("/tmp/auto-agent-tauri-sidecar.log"))
        .stderr(log_stdio("/tmp/auto-agent-tauri-sidecar.log"))
        .spawn()
        .map_err(|e| format!("failed to spawn sidecar ({python} -m app.worker.daemon): {e}"))
}

fn spawn_sidecar_bundled(path: &PathBuf) -> Result<Child, String> {
    let mut cmd = Command::new(path);
    if let Some(cwd) = bundled_process_cwd(path) {
        cmd.current_dir(cwd);
    }
    cmd.args(["serve", "--host", "127.0.0.1", "--port", "3921"])
        .stdout(log_stdio("/tmp/auto-agent-tauri-sidecar.log"))
        .stderr(log_stdio("/tmp/auto-agent-tauri-sidecar.log"))
        .spawn()
        .map_err(|e| format!("failed to spawn bundled sidecar ({path:?}): {e}"))
}

fn spawn_cloud(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<RuntimeState>();
    let mut guard = state.cloud.lock().map_err(|e| e.to_string())?;
    if guard.is_some() {
        return Ok(());
    }
    if cfg!(debug_assertions) {
        *guard = Some(spawn_cloud_dev()?);
    } else if let Some(path) = resolve_bundled_binary("auto-agent-cloud") {
        *guard = Some(spawn_cloud_bundled(&path)?);
    }
    Ok(())
}

fn spawn_sidecar(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<RuntimeState>();
    let mut guard = state.sidecar.lock().map_err(|e| e.to_string())?;
    if guard.is_some() {
        return Ok(());
    }
    if cfg!(debug_assertions) {
        *guard = Some(spawn_sidecar_dev()?);
    } else if let Some(path) = resolve_bundled_binary("auto-agent-runtime") {
        *guard = Some(spawn_sidecar_bundled(&path)?);
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
    stop_child(&state.sidecar);
    stop_child(&state.cloud);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(RuntimeState {
            sidecar: Mutex::new(None),
            cloud: Mutex::new(None),
        })
        .setup(|app| {
            if let Err(e) = spawn_cloud(app.handle()) {
                eprintln!("auto-agent: cloud spawn failed (UI will still open): {e}");
            }
            if let Err(e) = spawn_sidecar(app.handle()) {
                eprintln!("auto-agent: sidecar spawn failed (UI will still open): {e}");
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

            Ok(())
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
