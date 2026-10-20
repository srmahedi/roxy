# Roxy Download Manager

A modern, feature-rich download manager built with Python and PyQt6. Roxy provides a sleek dark-themed interface with powerful multi-threaded download management capabilities inspired by Free Download Manager (FDM).

**Note: Roxy is currently Windows-only.**

![Windows](https://img.shields.io/badge/Windows-10%2F11-blue.svg)
![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.11.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## ✨ Key Features

- ⚡ **Multi-Threaded Engine**: Custom FDM-style parallel chunk downloading with range request verification, mirror URL fallback support, and OkHttp integration via JPype for enhanced HTTP performance.
- 🎬 **HLS / M3U8 Stream Downloader**: Automatic variant resolution (highest bitrate), multi-threaded segment fetching, AES-128 stream decryption, and seamless MP4 remuxing with ffmpeg support.
- 🧩 **Chrome Extension Integration**: Intercepts Chrome downloads automatically and forwards URLs with full browser session metadata (cookies, referrer, user agent, post data).
- 🔄 **Duplicate Download Handling**: FDM-style duplicate detection prompt offering **Overwrite**, **Download Again** with sequence numbering (`file (1).ext`), or **Skip**.
- ⏯️ **Smart Pause & Resume**: Full resume capability for interrupted or paused downloads with `.temp` file state persistence.
- 🚀 **Speed Control & Monitoring**: Per-download bandwidth speed limiting and live download rate calculation.
- 📡 **Real-time Disk Tracking**: Live file system tracking using `watchdog` and download state persistence across application restarts.
- 🔒 **Single Instance Management**: Ensures only one Roxy instance runs at a time with socket-based inter-process communication.
- 🌐 **roxy:// Protocol Support**: Custom URL protocol handler for seamless integration with system and browser workflows.

---

## 🚀 Getting Started

### Requirements
- **Windows 10 / 11**
- **Python 3.8+**
- Python Dependencies: `PyQt6`, `watchdog`, `requests`, `urllib3`, `cryptography`, `JPype1`
- Optional: `ffmpeg` (for HLS stream remuxing to MP4)

### Quick Setup

```bash
# 1. Clone repository
git clone https://github.com/srmahedi/roxy.git
cd roxy

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch application
python main.py
```

---

## 🌐 Chrome Extension Setup

1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** in the top-right toggle.
3. Click **Load unpacked** and select the `Roxy-ext` folder from this repository.
4. Launch Roxy (`python main.py`). 
5. Any download initiated in Chrome will automatically transfer to Roxy via the local REST API (`http://localhost:12580`).

---

## 🏗️ Project Architecture

```
roxy/
├── main.py                     # Main application entry point & single-instance lock
├── roxy_launcher.py            # Companion launcher (Port 12579)
├── models/
│   ├── download_item.py        # Core download state machine & signal dispatcher
│   └── download_table_model.py # PyQt table view model & progress delegates
├── ui/
│   ├── main_window.py          # Main GUI window & duplicate interceptor
│   ├── title_bar.py            # Frameless dark window title bar
│   ├── add_url_dialog.py       # Add URL dialog interface
│   ├── duplicate_dialog.py     # Duplicate download choice modal (Overwrite/Rename/Skip)
│   └── custom_table_view.py    # Custom styled table view component
├── utils/
│   ├── download_engine.py      # Multi-threaded chunk download engine (OkHttp + requests)
│   ├── hls_engine.py           # HLS M3U8 stream parser & segment stitcher
│   ├── file_monitor.py         # Watchdog real-time file monitor
│   ├── persistence.py          # JSON download state persistence
│   ├── helpers.py              # Path, filename, and unique path helpers
│   └── constants.py            # Application constants & dark theme stylesheet
├── server/
│   ├── api_server.py           # Local HTTP REST API server (Port 12580)
│   └── single_instance.py      # Single instance socket lock listener (Port 12581)
├── okhttp/                     # OkHttp JAR files for Java HTTP client integration
│   ├── okhttp-jvm-5.5.0.jar
│   ├── okio-jvm-3.18.1.jar
│   ├── kotlin-stdlib-2.1.21.jar
│   └── annotations-13.0.jar
└── Roxy-ext/                   # Chrome extension source files
```

---

## 🔧 Building Standalone Executable

### PyInstaller Build
```bash
# Build main application executable
pyinstaller --clean --noconfirm --windowed --name Roxy --icon icon.ico main.py

# Build companion launcher
pyinstaller --clean --noconfirm --windowed --onefile --name roxy-launcher --icon icon.ico roxy_launcher.py
```

### Inno Setup Installer
- Open `setup.iss` with [Inno Setup Compiler](https://jrsoftware.org/isinfo.php) and click **Compile** to generate a single setup `.exe` installer.

---

## ⚙️ Configuration & Ports

- **State Storage**: `%LOCALAPPDATA%\Roxy_Download_Manager\downloads_state.json`
- **Port 12579**: Roxy Launcher Server (receives URLs from Chrome extension)
- **Port 12580**: Local REST API Server for Chrome extension communication
- **Port 12581**: Single-instance mutex socket listener

---

## � Technical Details

### Download Engine Architecture
- **Primary Backend**: OkHttp via JPype (Java HTTP client) for optimal performance
- **Fallback Backend**: Python `requests` library with retry logic
- **Multi-threading**: Up to 4 concurrent download threads per file
- **Chunk Management**: Adaptive section sizing (minimum 1MB per section)
- **Resume Support**: Automatic detection and utilization of HTTP Range requests
- **Special Handling**: Auto-detection and single-thread fallback for problematic servers (e.g., Google Drive)

### HLS Stream Processing
- **Master Playlist Support**: Automatic selection of highest bitrate variant
- **Segment Downloads**: Multi-threaded segment fetching (up to 4 concurrent)
- **Encryption**: AES-128 decryption with PKCS7 padding removal
- **Remuxing**: Optional ffmpeg-based TS to MP4 conversion
- **Fallback**: Direct TS file output if ffmpeg unavailable

### HTTP Features
- **Retry Strategy**: Configurable retry with exponential backoff
- **Timeout Configuration**: 30-second connection/read/write timeouts
- **Compression Handling**: Disabled to ensure reliable range requests
- **Mirror Support**: Fallback URL system for enhanced reliability

---

## �📄 License

Distributed under the **MIT License**. See `LICENSE` for details.
