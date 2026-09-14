# Roxy Download Manager

A modern, feature-rich download manager built with Python and PyQt6. Roxy provides a sleek dark-themed interface with powerful multi-threaded download management capabilities inspired by Free Download Manager (FDM).

**Note: Roxy is currently Windows-only.**

![Windows](https://img.shields.io/badge/Windows-10%2F11-blue.svg)
![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.11.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## ✨ Key Features

- ⚡ **Multi-Threaded Engine**: Custom FDM-style parallel chunk downloading with range request verification and mirror URL fallback support.
- 🎬 **HLS / M3U8 Stream Downloader**: Automatic variant resolution (highest bitrate), segment fetching, AES-128 stream decryption, and seamless MP4 remuxing.
- 📁 **Google Drive Resolver**: Automatic bypass and resolution of Google Drive warning confirmation pages for direct file downloads.
- 🧩 **Chrome Extension Integration**: Intercepts Chrome downloads automatically and forwards URLs with full browser session metadata (cookies, referrer, user agent).
- 🔄 **Duplicate Download Handling**: FDM-style duplicate detection prompt offering **Overwrite**, **Download Again** with sequence numbering (`file (1).ext`), or **Skip**.
- ⏯️ **Smart Pause & Resume**: Full resume capability for interrupted or paused downloads.
- 🚀 **Speed Control & Monitoring**: Per-download bandwidth speed limiting and live download rate calculation.
- 📡 **Real-time Disk Tracking**: Live file system tracking using `watchdog` and download state persistence across application restarts.

---

## 🚀 Getting Started

### Requirements
- **Windows 10 / 11**
- **Python 3.8+**
- Python Dependencies: `PyQt6`, `watchdog`, `requests`, `urllib3`, `cryptography`

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
├── roxy_host.py                # Companion launcher host script
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
│   ├── download_engine.py      # Multi-threaded chunk download engine
│   ├── hls_engine.py           # HLS M3U8 stream parser & segment stitcher
│   ├── gdrive_resolver.py     # Google Drive download link resolver
│   ├── file_monitor.py         # Watchdog real-time file monitor
│   ├── persistence.py          # JSON download state persistence
│   └── helpers.py              # Path, filename, and unique path helpers
├── server/
│   ├── api_server.py           # Local HTTP REST API server (Port 12580)
│   └── single_instance.py      # Single instance socket lock listener (Port 12581)
└── Roxy-ext/                   # Chrome extension source files
```

---

## 🔧 Building Standalone Executable

### PyInstaller Build
```bash
# Build main application executable
pyinstaller --noconfirm --windowed --name Roxy --icon icon.ico main.py

# Build companion launcher host (optional)
pyinstaller --noconfirm --windowed --onefile --name roxy-host --icon icon.ico roxy_host.py
```

### Inno Setup Installer
- Open `setup.iss` with [Inno Setup Compiler](https://jrsoftware.org/isinfo.php) and click **Compile** to generate a single setup `.exe` installer.

---

## ⚙️ Configuration & Ports

- **State Storage**: `%LOCALAPPDATA%\Roxy_Download_Manager\downloads_state.json`
- **Port 12580**: Local REST API Server for Chrome extension communication
- **Port 12581**: Single-instance mutex socket listener

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for details.
