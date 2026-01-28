# RATA-N (Next Generation) Rewrite Proposal

This document outlines two strategic paths for evolving RATA into a sophisticated, cross-platform audio solution with a web interface.

## 1. Executive Summary

The goal is to transform the existing script into a robust system service ("RATA-N") that:
*   Runs on **x86 and ARM** (Raspberry Pi).
*   Deploys as a **single binary** (or container).
*   Provides a **Web Interface** for management.
*   Removes the external **VLC dependency**.
*   Maintains **EUPL 1.2** compliance.

Two options are presented:
1.  **Rust Rewrite (Recommended):** Best for performance, stability, single-binary distribution, and cross-compilation.
2.  **Python Refactor:** Best for rapid development and leveraging the existing Python ecosystem, but harder to distribute as a single binary for ARM.

---

## Option A: The Rust Rewrite (Recommended)

This option involves rewriting the application from scratch in **Rust**. Rust is ideal for system services due to its memory safety, zero-cost abstractions, and excellent cross-compilation tooling.

### Tech Stack
*   **Language:** Rust (2021 Edition)
*   **Web Server:** `Axum` (High performance, ergonomic, runs on Tokio)
*   **Async Runtime:** `Tokio`
*   **Audio Playback:** `Rodio` (Pure Rust audio playback) + `Symphonia` (Decoding MP3/AAC/WAV) + `Cpal` (Device handling). *Replaces VLC.*
*   **Frontend:** `HTMX` + `TailwindCSS` (served by Axum). Assets embedded into the binary using `rust-embed`.
*   **Configuration:** `Figment` or `Config` crate (TOML support).
*   **Logging:** `Tracing` (Structured logging).

### Architecture
The application will operate as a multi-threaded system using an Actor-like model:
1.  **Core/Main Thread:** Initializes the `Tokio` runtime.
2.  **Audio Actor (Thread):** A dedicated thread for the `Rodio` sink to ensure gapless playback and prevent audio stuttering during high CPU load. Receives commands (Play, Stop, Volume) via a channel.
3.  **Scheduler Task (Async):** A Tokio task that checks the schedule every minute and sends commands to the Audio Actor.
4.  **Web Server Task (Async):** Serves the UI and API. Communicates with the Audio Actor and Scheduler via shared state (`Arc<RwLock<AppState>>`) and channels.

### Pros & Cons
| Pros | Cons |
| :--- | :--- |
| **True Single Binary:** Compiles everything (code + assets) into one executable. | **Dev Curve:** Steeper learning curve than Python. |
| **Cross-Compilation:** The `cross` tool makes building for Raspberry Pi from a PC trivial. | **Compilation Time:** Slower build times than Python interpretation. |
| **Resource Usage:** Extremely low CPU/RAM footprint. | |
| **Stability:** "If it compiles, it works" reliability. | |

### Roadmap
1.  **Prototype:** Basic audio playback with `rodio` and device selection.
2.  **Core:** Implement Scheduler and Config logic.
3.  **Web:** Add Axum server and basic HTMX frontend.
4.  **Packaging:** Setup GitHub Actions for cross-compiling releases.

---

## Option B: The Python Refactor

This option modernizes the current codebase, adding a web UI and replacing VLC, while keeping Python as the core.

### Tech Stack
*   **Language:** Python 3.11+
*   **Web Framework:** `NiceGUI` (Built on FastAPI + Vue.js). Excellent for creating local device interfaces quickly.
*   **Audio Playback:** `miniaudio` (Python bindings). A self-contained dependency-free audio library. *Replaces VLC.*
*   **Packaging:** `PyInstaller` (Bundles Python interpreter and scripts).

### Architecture
1.  **Event Loop:** The main thread runs the `NiceGUI`/`FastAPI` async event loop.
2.  **Audio Service:** Runs in a separate `Thread` or `Process` to avoid blocking the Web UI (Python GIL limitations).
3.  **Scheduler:** Uses `APScheduler` (Async) to manage timing.
4.  **UI:** Real-time WebSocket connection syncs the UI state with the backend.

### Pros & Cons
| Pros | Cons |
| :--- | :--- |
| **Speed:** Extremely fast development cycle. | **Distribution:** "Single Binary" is a hack (self-extracting archive). Startup is slower. |
| **Ecosystem:** Massive library availability. | **Cross-Compile:** Hard. You must build the binary *on* the target OS (or use QEMU). |
| **Simplicity:** Easier for less experienced contributors to modify. | **Runtime Errors:** Python is less strict; bugs may appear at runtime. |

### Roadmap
1.  **Refactor:** Replace `python-vlc` with `miniaudio`.
2.  **UI:** Implement `NiceGUI` interface for config editing.
3.  **Service:** Integrate systemd management into the UI.
4.  **Build:** Create Docker containers for building ARM binaries.

---

## Feature Comparison Matrix

| Feature | Rust (RATA-N) | Python (RATA-N) |
| :--- | :--- | :--- |
| **Single Binary** | Native, small (~10MB) | Bundled, large (~50MB+) |
| **Cross-Platform Build** | Easy (`cross build`) | Hard (Build on Target) |
| **Memory Usage** | < 20MB | > 100MB |
| **Audio Dependency** | `rodio` (Pure Rust) | `miniaudio` (C Binding) |
| **Web UI Responsiveness**| Instant | Fast (WebSocket) |
| **Hot Reload** | Yes | Yes |

## Licensing & Compliance

Both options are designed to be compatible with **EUPL 1.2**.

*   **Rust Crates:** `Rodio`, `Axum`, `Tokio` use **MIT** or **Apache 2.0**. These are permissive licenses compatible with EUPL 1.2 (which is copyleft).
*   **Python Libraries:** `NiceGUI` (MIT), `miniaudio` (MIT).
*   **EUPL 1.2:** Allows linking with compatible permissive licenses. The final compiled work can be distributed under EUPL 1.2.

## Recommendation

**Go with Rust.**
The requirement for "Cross-platform target (ARM/x86)" and "Single Binary" strongly favors Rust. Python's single-binary solutions are often fragile and difficult to cross-compile. Rust's ecosystem for system services is mature, and `rodio` provides the necessary audio capabilities without the weight of VLC.
