# Roxy Download Manager

A modern, feature-rich download manager built with Python, PyQt6, and curl. Roxy provides a sleek dark-themed interface with powerful download management capabilities inspired by popular download managers like Free Download Manager (FDM).

**Note: Roxy is currently Windows-only.**

![Roxy Download Manager](https://img.shields.io/badge/Windows-10/11-blue.svg)
![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.11.0-green.svg)
![watchdog](https://img.shields.io/badge/watchdog-6.0.0-orange.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/srmahedi/roxy.git
cd roxy

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

> **⚠️ Platform Requirement**: Roxy is currently Windows-only. Requires Windows 10/11 with Python 3.8+ and curl installed.

## 📋 Requirements

- **Windows 10/11** - Roxy is Windows-only
- **Python 3.8+** - [Download here](https://www.python.org/downloads/)
- **PyQt6 6.11.0** - GUI framework (installed via requirements.txt)
- **watchdog 6.0.0** - File system monitoring (installed via requirements.txt)
- **curl** - Must be installed and available in PATH

### Installing curl on Windows

Download from [curl official website](https://curl.se/windows/) or use Chocolatey:
```bash
choco install curl
```

Verify installation by running:
```bash
curl --version
```

## 📦 Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/srmahedi/roxy.git
cd roxy
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Run the Application

```bash
python main.py
```

That's it! Roxy should now launch with its dark-themed interface.

## 🎮 Usage

### Adding Downloads

1. Click the **"Add URL"** button in the toolbar
2. Enter the URL of the file you want to download
3. Choose a save location (defaults to your Downloads folder)
4. Optionally set a speed limit (0 = unlimited)
5. Click **OK** to start the download

## 🌐 Chrome Extension Integration

Roxy includes a Chrome extension that automatically intercepts downloads from Chrome and redirects them to Roxy.

### Setup Instructions

1. **Install the Extension**:
   - Open Chrome and navigate to `chrome://extensions/`
   - Enable **"Developer mode"** in the top right corner
   - Click **"Load unpacked"** and select the `Roxy-ext` folder

2. **Start the Launcher**:
   ```bash
   python roxy_launcher.py
   ```
   - This starts a background server that receives download URLs from the Chrome extension
   - The launcher is configured to launch Roxy from `C:\Users\[Username]\AppData\Local\Programs\Roxy\Roxy.exe`

3. **Automatic Downloads**:
   - When you download files in Chrome, they will be automatically intercepted
   - The extension cancels Chrome's download and sends the URL to Roxy
   - Roxy will automatically come to the front and start the download

### Extension Features

- **Automatic Interception** - Catches downloads before Chrome starts them
- **URL Redirection** - Sends download URLs to Roxy for better management
- **Auto-Focus** - Brings Roxy to the front when new downloads are added
- **Windows-Specific Integration** - Uses Windows executable paths and process management
- **Enable/Disable Toggle** - Click the extension icon to enable or disable the extension
  - When enabled (default): Downloads are intercepted and sent to Roxy
  - When disabled: Downloads are handled normally by Chrome
  - Badge shows "off" when the extension is disabled
  - Useful if Roxy fails to download something and you want Chrome to handle it instead



## 🔧 Building Executable

### PyInstaller

1. **Create the host server**:
```bash
pyinstaller --noconfirm --windowed --onefile --name roxy-host --icon icon.ico roxy_launcher.py
```

2. **Create the main app**:
```bash
pyinstaller --noconfirm --windowed --name Roxy --icon icon.ico main.py
```

### Inno Setup (Windows Installer)

1. **Install Inno Setup** - Download from [jrsoftware.org](https://jrsoftware.org/isinfo.php)

2. **Run the installer script**:
```bash
setup.iss
```

This will create a Windows installer with both the main application and the launcher server.

## � Platform Support

**Current Status**: Roxy is **Windows-only**.

## �🔍 Troubleshooting

### "curl not found" Error

**Solution**: Ensure curl is installed and available in your system PATH. Test by running:
```bash
curl --version
```

### Downloads Won't Start

**Possible causes**:
- URL is not accessible
- No write permissions to the save location
- Unstable internet connection

**Solution**: Check the URL, verify folder permissions, and test your internet connection.

### Resume Not Working

**Note**: Some servers don't support resume functionality. In such cases, the download will restart from the beginning.

### Chrome Extension Not Working

**Checklist**:
- ✅ Ensure `roxy_launcher.py` is running in the background
- ✅ Check that the extension is properly loaded in Chrome
- ✅ Verify that roxy_launcher port is not blocked by firewall
- ✅ Check Chrome extension console for errors (F12 → Extensions)

### Multiple Downloads Not Working

**Solution**:
- Ensure the launcher server is running
- Check that Roxy's HTTP API server is accessible on main app port
- Restart both the launcher and Roxy if issues persist

## ⚙️ Configuration

### Customizing Launcher Path

The launcher uses a hardcoded path to Roxy.exe. To customize this, edit `roxy_launcher.py` and change the `default_path` variable.

## 📄 License

This project is open source and available under the **MIT License**.

## 🙏 Credits

Built with:
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - Python GUI framework
- [curl](https://curl.se/) - Command line tool for transferring data with URLs

## 📖 Acknowledgments

Inspired by popular download managers like Free Download Manager (FDM), aiming to provide a similar experience with a modern Python-based implementation.
