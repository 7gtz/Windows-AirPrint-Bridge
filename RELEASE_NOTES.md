## v1.1.1 - 2026-08-12

### 🌐 Multi-PC Network & Display Enhancements
- **Multi-PC Network Identification:** Dynamic printer naming incorporating host PC name and printer name (`Printer (PC-NAME)`).
- **Unique mDNS UUIDs:** Machine-specific mDNS UUID generation (`uuid5` on `Printer@Hostname`) preventing iOS/AirPrint device collision across multiple PCs running the bridge on the same LAN.
- **Enhanced IPP & mDNS Attributes:** Updated `printer-make-and-model`, `printer-info`, `printer-location`, and mDNS TXT `note` fields for clear printer discovery UI on iOS, macOS, and Android.

## v1.1.0 - 2026-08-12

### 🛠️ Windows Service & Compatibility Fixes
- **Windows Service SCM Error 7039 Fixed:** Updated PyInstaller build settings to `--console` mode to ensure PID consistency with Windows Service Control Manager.
- **Persistent Service Logging:** Fixed log file path resolution when frozen with PyInstaller (`sys.executable` directory) so logs persist properly.
- **IPP Operation Expansion:** Added support for `Get-Job-Attributes` (`0x0009`) and `Cancel-Job` (`0x0008`) required by iOS PrintKit post-print routines.

### 🔒 Security & Code Quality Improvements
- **Document Extraction Safety:** Removed unsafe brute-force `0x03` delimiter fallback byte search that could truncate binary payloads.
- **XSS Prevention:** HTML-escaped printer names rendered in Web / HTTP status views.
- **Temp File Hardening:** Switched print job temp file creation to `tempfile.NamedTemporaryFile` with explicit cleanup in `finally` blocks.
- **UUID Compliance:** Standardized UUID generation across mDNS and IPP responses using RFC 4122 `uuid.uuid5()`.
- **Diagnostic Tool Cleanups:** Replaced hardcoded IP addresses with dynamic local IP auto-detection across `diagnose.py`, `decode_ipp.py`, and `quick_check.py`.

## v1.0.1 - 2026-08-11

### 🐛 Bug Fixes
- **Interactive Mode Fallback**: Fixed an issue (Error 1063) where running the standalone executable directly would crash. It now gracefully falls back to interactive debugging mode if it's not launched by the Service Control Manager.
- **Documentation**: Added troubleshooting steps for users with virtual printers (like RustDesk) that take over the Windows Default Printer setting, causing jobs to print to nowhere.

## v1.0.0 - 2026-08-10

### 🚀 New Features
- **Standalone Installer:** Now available as a fully automated Windows setup wizard that installs and runs the bridge as a background Windows Service.
- Print PDFs natively on Windows via PyMuPDF + win32 DC integration.
- Scale and center PDF pages to the printable area.
- Add URF (Apple Raster) support and AirPrint attributes.
- Register AirPrint subtype as a separate mDNS service.
- Enhance mDNS AirPrint advertisement for better iOS/macOS discovery.

### ⚡ Improvements
- Add IPP decoder and various AirPrint compatibility fixes.

### 📚 Documentation
- Revamp README for the Windows AirPrint Bridge project.
- Add supported devices documentation.

### 🏗️ Infrastructure & Maintenance
- Add PyInstaller (`build.ps1`) and Inno Setup (`installer.iss`) build scripts for generating distributable Windows executables.
- Add `diagnose.py` mDNS + IPP AirPrint diagnostic script for debugging.
- Add `quick_check.py` IPP probe script.
