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
