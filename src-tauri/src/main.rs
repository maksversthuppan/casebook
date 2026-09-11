// Prevents an extra console window from popping up alongside the app's own
// window on Windows in release builds - standard Tauri template line.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Startup sequence (docs/desktop-app-roadmap.md Phase C):
//!
//! 1. Launch both sidecars (backend PyInstaller onedir exe, frontend's
//!    portable-Node + Next.js standalone build), bundled as Tauri
//!    `resources` rather than `externalBin` - both are folders of files that
//!    must ship together, not the single self-contained binary `externalBin`
//!    expects.
//! 2. Poll each one's health endpoint until both respond.
//! 3. Only then show the main window, pointed at the frontend sidecar's own
//!    local URL - `app.windows` is empty in tauri.conf.json, so nothing is
//!    shown (and nothing errors on a not-yet-listening port) before this.
//! 4. On exit, kill both sidecar processes - nothing may outlive the app,
//!    matching the discipline already in `backend/app/dcms/{session,browser}.py`.

use std::io;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

const BACKEND_PORT: u16 = 8743;
const FRONTEND_PORT: u16 = 3100;

/// First run downloads Chromium (tens of MB) before the backend answers
/// `/api/health` at all - this has to be generous, not a normal request
/// timeout.
const HEALTH_TIMEOUT: Duration = Duration::from_secs(180);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(500);

/// Holds both sidecar processes so the exit handler can kill them. `None`
/// until `setup`'s background thread has spawned them.
struct Sidecars(Mutex<Option<(Child, Child)>>);

fn wait_healthy(url: &str, deadline: Instant) -> bool {
    while Instant::now() < deadline {
        let got_200 = ureq::get(url)
            .timeout_connect(Duration::from_secs(2))
            .timeout_read(Duration::from_secs(2))
            .call()
            .map(|resp| resp.status() == 200)
            .unwrap_or(false);
        if got_200 {
            return true;
        }
        std::thread::sleep(HEALTH_POLL_INTERVAL);
    }
    false
}

fn spawn_backend(resource_dir: &Path) -> io::Result<Child> {
    let dir = resource_dir.join("backend");
    Command::new(dir.join("casebook-backend.exe"))
        .current_dir(&dir)
        .spawn()
}

fn spawn_frontend(resource_dir: &Path) -> io::Result<Child> {
    let dir = resource_dir.join("frontend");
    Command::new(dir.join("node.exe"))
        .arg("server.js")
        .current_dir(&dir)
        .env("PORT", FRONTEND_PORT.to_string())
        .env("BACKEND_URL", format!("http://127.0.0.1:{BACKEND_PORT}"))
        .spawn()
}

/// Kills both sidecars if they're still running. Best-effort: a process that
/// already exited (crashed, or was already reaped) is not an error here.
fn kill_sidecars(sidecars: &Sidecars) {
    if let Some((mut backend, mut frontend)) = sidecars.0.lock().unwrap().take() {
        let _ = backend.kill();
        let _ = frontend.kill();
    }
}

fn main() {
    let app = tauri::Builder::default()
        .manage(Sidecars(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let resource_dir: PathBuf = handle
                    .path()
                    .resource_dir()
                    .expect("resource dir must resolve - bundle.resources in tauri.conf.json");

                let backend = spawn_backend(&resource_dir)
                    .expect("failed to launch backend sidecar (resources/backend)");
                let frontend = spawn_frontend(&resource_dir)
                    .expect("failed to launch frontend sidecar (resources/frontend)");

                *handle.state::<Sidecars>().0.lock().unwrap() = Some((backend, frontend));

                let deadline = Instant::now() + HEALTH_TIMEOUT;
                let backend_ok =
                    wait_healthy(&format!("http://127.0.0.1:{BACKEND_PORT}/api/health"), deadline);
                let frontend_ok = backend_ok
                    && wait_healthy(&format!("http://127.0.0.1:{FRONTEND_PORT}/"), deadline);

                if !backend_ok || !frontend_ok {
                    eprintln!(
                        "casebook: sidecars never became healthy within {:?} \
                         (backend ok: {backend_ok}, frontend ok: {frontend_ok}) - not opening a window",
                        HEALTH_TIMEOUT
                    );
                    kill_sidecars(&handle.state::<Sidecars>());
                    handle.exit(1);
                    return;
                }

                let window_handle = handle.clone();
                handle
                    .run_on_main_thread(move || {
                        WebviewWindowBuilder::new(
                            &window_handle,
                            "main",
                            WebviewUrl::External(
                                format!("http://127.0.0.1:{FRONTEND_PORT}")
                                    .parse()
                                    .expect("hardcoded URL is always valid"),
                            ),
                        )
                        .title("Casebook")
                        .inner_size(1400.0, 900.0)
                        .build()
                        .expect("failed to open main window");
                    })
                    .expect("failed to schedule window creation on the main thread");
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the tauri application");

    app.run(|app_handle, event| {
        // Fires once the last window closes (or `handle.exit()` above ran) -
        // the one place sidecar cleanup can't be skipped, matching "nothing
        // outlives the process" for the app itself.
        if let RunEvent::Exit = event {
            kill_sidecars(&app_handle.state::<Sidecars>());
        }
    });
}
