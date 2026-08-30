# Windows AirPrint Bridge

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgray.svg)](https://www.microsoft.com/windows)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![GitHub release](https://img.shields.io/github/v/release/salmanasmat/Windows-AirPrint-Bridge?color=brightgreen)](https://github.com/salmanasmat/Windows-AirPrint-Bridge/releases/latest)
[![GitHub All Releases](https://img.shields.io/github/downloads/salmanasmat/Windows-AirPrint-Bridge/total)](https://github.com/salmanasmat/Windows-AirPrint-Bridge/releases)

A production-ready, standalone Python script that acts as an AirPrint and IPP (Internet Printing Protocol) bridge server. It enables iOS (AirPrint) and Android (IPP Everywhere) devices connected to the same network to print documents to Windows printers—including legacy, offline printers that don't support Ethernet or Wi-Fi connections. Transform any offline printer into a network-accessible device, enabling seamless printing from phones and tablets over your local network.

## Features

- **Native Zero-Configuration Discovery:** Broadcasts strictly compliant mDNS `_ipp._tcp.local.` and Apple AirPrint `_universal._sub._ipp._tcp.local.` services. Automatically binds to your active network interface.
- **Strict iOS 18 Compatibility:** Implements Apple's required TXT record properties (like deterministic `UUID` matching and URF capability strings) to pass the strict iOS 18 discovery validation checks.
- **HTTP/1.1 & Chunked Transfer Encoding:** A custom HTTP server that natively handles the `Expect: 100-continue` and chunked HTTP payloads sent by iOS for large print jobs.
- **Robust Headless PDF Rendering:** Avoids unreliable Windows shell commands (like `ShellExecute printto`) which break when Microsoft Edge is the default PDF viewer. Instead, it uses `PyMuPDF` to render documents natively.
- **Scale-to-Fit:** Automatically detects your printer's exact printable area (DPI and physical dimensions) and mathematically scales the document to fit perfectly and center on the page, preventing clipping or distortion.

## Supported Devices

By strictly adhering to Apple AirPrint and standard IPP Everywhere requirements, this service achieves seamless driverless printing across platforms:

- **iOS & iPadOS:** Fully tested and verified. Supports virtually all versions from **iOS 4.2 up through iOS 18+**. Passes strict zero-configuration checks introduced in iOS 16–18.
- **macOS:** Natively supported via Bonjour / AirPrint discovery.
- **Android:** Natively supported via the Android Default Print Service and Mopria (IPP Everywhere).

> [!TIP]
> **v1.2.0 Release Highlights:** v1.2.0 introduces full native Android discovery compatibility (synchronizing mDNS/IPP UUIDs, enforcing RFC 8011 attribute compliance, and adding PWG-Raster format support) alongside existing iOS AirPrint support.

## Android Configuration (Important)

Unlike iOS (where AirPrint is always enabled by default in the sharing sheet), **Android often has its built-in print service disabled by default** depending on the device manufacturer (e.g., Samsung, Xiaomi, OnePlus, Motorola).

To make your Windows printer discoverable on Android:

1. Open **Settings** on your Android device.
2. Navigate to **Connected devices → Connection preferences → Printing** *(or search for **"Printing"** in the Settings search bar)*.
3. Tap **Default Print Service** and toggle the switch to **ON**.
4. Now, open any photo, document, or webpage, tap **Share → Print** (or menu **Print**), and your Windows printer (`<Printer Name> (<PC-Hostname>)`) will appear in the printer selection dropdown.

> [!NOTE]
> - **Alternative Print Service:** If your device manufacturer removed the Default Print Service, install the official [Mopria Print Service](https://play.google.com/store/apps/details?id=org.mopria.clara) app from Google Play.
> - **Wi-Fi Network / AP Isolation:** Ensure your Android phone and Windows PC are connected to the same Wi-Fi network and subnet. Make sure **"AP Isolation" / "Client Isolation"** or **"Guest Network"** is disabled in your Wi-Fi router settings so mDNS (UDP 5353) multicast traffic can pass between devices.

## Configuring the Printer

AirPrint Bridge no longer relies on the Windows **default printer** — you tell it explicitly which printer to share, and it prints through that printer's own existing Windows configuration (input tray, paper type, ReadyPrint, etc.), unmodified. This means the Windows default printer can stay set to something else (e.g. `Microsoft Print to PDF`) and the bridge will still print to the printer you configured.

1. Find the exact Windows printer name:

   ```powershell
   AirPrintBridge.exe --list-printers
   ```

   ```
   Available Windows printers:

     1. Brother HL-L2350DW
     2. Microsoft Print to PDF
     3. OneNote
   ```

2. Create `config.json` next to `AirPrintBridge.exe` (a starter `config.json.example` is installed alongside it — copy/rename it) with the exact name from step 1:

   ```json
   {
       "printer": "Brother HL-L2350DW"
   }
   ```

3. Start (or restart) the service. At startup the bridge validates the configured printer and logs the result:

   ```
   Configured printer: Brother HL-L2350DW
   Printer exists: yes
   Printer status: ready
   ```

   If the name doesn't match a printer Windows knows about, the bridge logs the error and exits rather than silently falling back to the default printer — this avoids accidentally routing a print job to the wrong device.

> [!TIP]
> For quick testing without editing `config.json`, pass `--printer` directly — it takes priority over `config.json`:
> ```powershell
> AirPrintBridge.exe --printer "Brother HL-L2350DW"
> ```

## Installation (Recommended)

The easiest way to install and run AirPrint Bridge on Windows is using the pre-compiled installer. **No Python installation or dependencies are required.** Everything is bundled into a self-contained background Windows Service that automatically starts when your PC boots.

1. Download the latest `AirPrintBridge_Setup_v1.2.0.exe` from the [Releases page](https://github.com/salmanasmat/Windows-AirPrint-Bridge/releases/latest).
2. Run the installer as Administrator and follow the setup wizard.
3. Set up `config.json` as described in [Configuring the Printer](#configuring-the-printer) above.
4. The AirPrint Bridge service will automatically start in the background.
5. On your iOS or Android device (connected to the same Wi-Fi network), open a document or photo, tap **Print**, and select your Windows printer.

## Development & Manual Setup (Developers)

If you prefer to run from source code or contribute to development:

### Prerequisites

- **Windows OS**
- **Python 3.8+**

Install required dependencies:

```powershell
pip install zeroconf pymupdf pillow pywin32
```

### Running from Source

1. Copy `config.json.example` to `config.json` and set `"printer"` to the exact Windows printer name (run `python airprint_bridge.py --list-printers` to see the available names).
2. Run the bridge script:

```powershell
python airprint_bridge.py
```

3. The server will detect your local IP address, validate the configured printer, bind to port `631` (the standard IPP port), and begin broadcasting on your local network.

### Building the Executable & Installer

To build the standalone executable and setup wizard from source:

```powershell
# 1. Build PyInstaller single-file console executable
.\build.ps1

# 2. Compile Inno Setup installer wizard (requires Inno Setup 6)
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" .\installer.iss
```

## Diagnostics and Troubleshooting

If your device cannot find the printer, you can run the included diagnostic script:

```powershell
python diagnose.py
```

### Common Issues

- **Firewall Blocking:** Ensure that **TCP Port 631** (IPP) and **UDP Port 5353** (mDNS/Bonjour) are allowed through the Windows Defender Firewall for inbound connections.
- **Ghost Processes:** If the script crashes or is terminated forcefully, a zombie Python process might hold port `631` open, preventing the script from restarting. You can forcefully kill any process using the port with:
  ```powershell
  $pidToKill = (netstat -ano | Select-String ":631" | Select-String "LISTENING").Line.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)[-1]; if ($pidToKill) { Stop-Process -Id $pidToKill -Force }
  ```
- **Different Subnets:** Your mobile device and Windows PC must be on the exact same local Wi-Fi subnet for mDNS multicast packets to reach the device.
- **Wrong printer / nothing prints:** AirPrint Bridge always prints through the printer named in `config.json` (or `--printer`), regardless of the Windows default printer — so a program silently changing your Windows default (RustDesk, a newly installed PDF printer, etc.) can't redirect jobs anymore. Check `airprint_bridge.log` for the `Configured printer: …` / `Printer exists: …` lines at startup to confirm which printer is actually in use, and update `config.json` if it's wrong.

## How It Works (Technical Architecture)

1. **mDNS Registration:** Uses a dual-instance `zeroconf` approach to simultaneously register the primary IPP service and the Apple-specific `_universal` subtype pointing to the same instance name in the local domain.
2. **IPP Binary Protocol:** The server implements a minimal IPP 1.1 / 2.0 binary protocol parser, handling `Print-Job`, `Validate-Job`, and `Get-Printer-Attributes` operations. It responds with mandatory and extended attributes required by modern iOS releases.
3. **Print Spooling:** When a document is received, it is dumped to a temporary file. The configured printer's own current DEVMODE (tray, paper type, ReadyPrint, etc. — whatever is set in Windows' Printer Properties) is read from the print queue via `win32print.GetPrinter()` and used unmodified to create the device context via `win32gui.CreateDC()` / `win32ui`; `fitz` (PyMuPDF) then draws the document natively into that DC, bypassing the problematic shell-based PDF printing methods. Because the DEVMODE is inherited rather than reconstructed, any printer settings you change in Windows apply automatically — no bridge configuration needed.
