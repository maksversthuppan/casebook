// Prevents an extra console window from popping up alongside the app's own
// window on Windows in release builds - standard Tauri template line.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Startup sequence (docs/desktop-app-roadmap.md Phase C, splash/logging pass):
//!
//! 1. Show a splash window immediately (`dist-stub/splash.html`) - there is
//!    otherwise nothing on screen at all until both sidecars are healthy,
//!    which used to read as a stuck launch on a first run whose Chromium
//!    download can take minutes.
//! 2. Launch both sidecars (backend PyInstaller onedir exe, frontend's
//!    portable-Node + Next.js standalone build), bundled as Tauri
//!    `resources` rather than `externalBin` - both are folders of files that
//!    must ship together, not the single self-contained binary `externalBin`
//!    expects. Both are spawned with no console window (Windows
//!    `CREATE_NO_WINDOW`) and with stdout/stderr redirected to real log
//!    files - giving the child process valid file handles this way, rather
//!    than none at all, is also what keeps a windowed-subsystem PyInstaller
//!    build's `sys.stdout`/`sys.stderr` from coming back `None` and crashing
//!    the first time anything tries to print.
//! 3. Poll each one's health endpoint until both respond, updating the
//!    splash's text from the backend's own status file each tick (the only
//!    channel available before uvicorn can answer `/api/health` at all).
//! 4. Only then show the main window, pointed at the frontend sidecar's own
//!    local URL, and close the splash - `app.windows` is empty in
//!    tauri.conf.json, so nothing else is shown before this.
//! 5. On exit, kill both sidecar processes - nothing may outlive the app,
//!    matching the discipline already in `backend/app/dcms/{session,browser}.py`.

use std::fs::{self, File};
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

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

/// `%LOCALAPPDATA%\casebook` - must match `_appdata_dir()` in
/// `backend/app/desktop/entrypoint.py` exactly; this is the one place
/// outside Python that name is spelled again.
fn appdata_dir() -> PathBuf {
    std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join("casebook")
}

fn status_path() -> PathBuf {
    appdata_dir().join("status.txt")
}

/// Windows-only: suppresses the console window a console-subsystem child
/// (both sidecars) would otherwise get auto-allocated. Stubbed out on other
/// platforms so `cargo check` keeps working on this Linux dev machine
/// (Cargo.toml: Windows is the only real target, but nothing stops a local
/// typecheck).
#[cfg(target_os = "windows")]
fn hide_window(cmd: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    cmd.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(target_os = "windows"))]
fn hide_window(_cmd: &mut Command) {}

/// Truncates and reopens `dir/name` for a sidecar's stdout+stderr. Truncated
/// rather than appended - one run's log is enough for support purposes, and
/// truncating means it can never grow unbounded across the life of the
/// install.
fn open_log(dir: &Path, name: &str) -> io::Result<File> {
    fs::create_dir_all(dir)?;
    File::create(dir.join(name))
}

fn wait_healthy(url: &str, deadline: Instant, splash: &WebviewWindow) -> bool {
    while Instant::now() < deadline {
        // The only channel available before uvicorn can answer HTTP at all -
        // entrypoint.py overwrites this file at each real startup milestone
        // (Chromium download, server start).
        if let Ok(status) = fs::read_to_string(status_path()) {
            let status = status.trim();
            if !status.is_empty() {
                set_splash_status(splash, status);
            }
        }

        let got_200 = ureq::get(url)
            .timeout(Duration::from_secs(2))
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

fn spawn_backend(resource_dir: &Path, log_dir: &Path) -> io::Result<Child> {
    let dir = resource_dir.join("backend");
    let out = open_log(log_dir, "backend.log")?;
    let err = out.try_clone()?;
    let mut cmd = Command::new(dir.join("casebook-backend.exe"));
    cmd.current_dir(&dir).stdout(out).stderr(err);
    hide_window(&mut cmd);
    cmd.spawn()
}

fn spawn_frontend(resource_dir: &Path, log_dir: &Path) -> io::Result<Child> {
    let dir = resource_dir.join("frontend");
    let out = open_log(log_dir, "frontend.log")?;
    let err = out.try_clone()?;
    let mut cmd = Command::new(dir.join("node.exe"));
    cmd.arg("server.js")
        .current_dir(&dir)
        .env("PORT", FRONTEND_PORT.to_string())
        .env("BACKEND_URL", format!("http://127.0.0.1:{BACKEND_PORT}"))
        .stdout(out)
        .stderr(err);
    hide_window(&mut cmd);
    cmd.spawn()
}

/// Kills both sidecars if they're still running. Best-effort: a process that
/// already exited (crashed, or was already reaped) is not an error here.
fn kill_sidecars(sidecars: &Sidecars) {
    if let Some((mut backend, mut frontend)) = sidecars.0.lock().unwrap().take() {
        let _ = backend.kill();
        let _ = frontend.kill();
    }
}

/// Runs from the Rust host side against the webview - not the webview
/// calling back into Tauri - so this needs no capability/permission grant
/// and no bundled `@tauri-apps/api`. `serde_json` gives a safely
/// JS-string-literal-escaped form of an arbitrary message for free.
fn set_splash_status(splash: &WebviewWindow, message: &str) {
    let Ok(js_string) = serde_json::to_string(message) else {
        return;
    };
    let _ = splash.eval(&format!(
        "var el = document.getElementById('status'); if (el) el.textContent = {js_string};"
    ));
}

fn create_splash(app: &tauri::AppHandle) -> tauri::Result<WebviewWindow> {
    WebviewWindowBuilder::new(app, "splash", WebviewUrl::App("splash.html".into()))
        .title("Casebook")
        .inner_size(360.0, 220.0)
        .resizable(false)
        .center()
        // Kept decorated (not chromeless) on purpose: if startup fails, the
        // splash stays open with the error shown in it rather than the app
        // silently exiting, and a normal title bar is the only way the
        // advocate has to close that window herself.
        .build()
}

fn main() {
    let app = tauri::Builder::default()
        .manage(Sidecars(Mutex::new(None)))
        .setup(|app| {
            let splash = create_splash(app.handle())?;

            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let resource_dir: PathBuf = handle
                    .path()
                    .resource_dir()
                    .expect("resource dir must resolve - bundle.resources in tauri.conf.json");
                let log_dir = appdata_dir().join("logs");

                // Stale text from a previous run (crashed, or simply old)
                // must never flash before this run's own first write.
                let _ = fs::remove_file(status_path());

                let backend = spawn_backend(&resource_dir, &log_dir)
                    .expect("failed to launch backend sidecar (resources/backend)");
                let frontend = spawn_frontend(&resource_dir, &log_dir)
                    .expect("failed to launch frontend sidecar (resources/frontend)");

                *handle.state::<Sidecars>().0.lock().unwrap() = Some((backend, frontend));

                let deadline = Instant::now() + HEALTH_TIMEOUT;
                let backend_ok = wait_healthy(
                    &format!("http://127.0.0.1:{BACKEND_PORT}/api/health"),
                    deadline,
                    &splash,
                );
                let frontend_ok = backend_ok
                    && wait_healthy(&format!("http://127.0.0.1:{FRONTEND_PORT}/"), deadline, &splash);

                if !backend_ok || !frontend_ok {
                    set_splash_status(
                        &splash,
                        &format!(
                            "Casebook could not start (backend ok: {backend_ok}, frontend ok: {frontend_ok}). \
                             Check the logs under %LOCALAPPDATA%\\casebook\\logs and close this window.",
                        ),
                    );
                    kill_sidecars(&handle.state::<Sidecars>());
                    // Deliberately not `handle.exit()` here: that would also
                    // tear down the splash, so the advocate would never see
                    // the message just written to it. The app quits once she
                    // closes this window instead (Tauri's default behaviour
                    // for the last remaining window).
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

                        if let Some(splash) = window_handle.get_webview_window("splash") {
                            let _ = splash.close();
                        }
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
