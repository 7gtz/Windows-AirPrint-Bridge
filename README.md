# Windows AirPrint Bridge

A production-ready, standalone Python script that acts as an AirPrint and IPP (Internet Printing Protocol) bridge server. It enables iOS (AirPrint) and Android (IPP Everywhere) devices connected to the same Wi-Fi network to print directly to a PC-connected printer natively—without requiring any third-party mobile apps.

## Features

- **Native Zero-Configuration Discovery:** Broadcasts strictly compliant mDNS `_ipp._tcp.local.` and Apple AirPrint `_universal._sub._ipp._tcp.local.` services. Automatically binds to your active Wi-Fi adapter to prevent multicast routing issues on multi-homed (Ethernet + Wi-Fi) machines.
- **Strict iOS 18 Compatibility:** Implements Apple's required TXT record properties (like deterministic `UUID` matching and URF capability strings) to pass the strict iOS 18 discovery validation phase.
- **HTTP/1.1 & Chunked Transfer Encoding:** A custom HTTP server that natively handles the `Expect: 100-continue` and chunked HTTP payloads sent by iOS for large print jobs.
- **Robust Headless PDF Rendering:** Avoids unreliable Windows shell commands (like `ShellExecute printto`) which break when Microsoft Edge is the default PDF viewer. Instead, it uses `PyMuPDF` to rasterize the PDF in-memory and `win32ui` to send it directly to the printer's Device Context (DC).
- **Scale-to-Fit:** Automatically detects your printer's exact printable area (DPI and physical dimensions) and mathematically scales the document to fit perfectly and center on the page, preventing cropping.

## Prerequisites

The script requires **Python 3.8+** and a Windows operating system.

Install the required Python packages:

```powershell
pip install zeroconf pymupdf pillow pywin32
```

## Usage

1. Set the printer you want to share as your **Default Printer** in Windows.
2. Run the bridge script:

```powershell
python airprint_bridge.py
```

3. The server will detect your local IP address and default printer, bind to port `631` (the standard IPP port), and begin broadcasting.
4. On your iOS or Android device (connected to the same Wi-Fi network), open a document or photo, tap **Print**, and your Windows printer should appear in the list.

## Diagnostics and Troubleshooting

If your device cannot find the printer, you can run the included diagnostic script:

```powershell
python diagnose.py
```

### Common Issues

- **Firewall Blocking:** Ensure that **TCP Port 631** (IPP) and **UDP Port 5353** (mDNS/Bonjour) are allowed through the Windows Defender Firewall for inbound connections.
- **Ghost Processes:** If the script crashes or is terminated forcefully, a zombie Python process might hold port `631` open, preventing the script from restarting. You can forcefully kill any process holding port 631 via PowerShell:
  ```powershell
  $pidToKill = (netstat -ano | Select-String ":631" | Select-String "LISTENING").Line.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)[-1]; if ($pidToKill) { Stop-Process -Id $pidToKill -Force }
  ```
- **Different Subnets:** Your mobile device and Windows PC must be on the exact same local Wi-Fi subnet for mDNS multicast packets to reach the device.

## How It Works (Technical Architecture)

1. **mDNS Registration:** Uses a dual-instance `zeroconf` approach to simultaneously register the primary IPP service and the Apple-specific `_universal` subtype pointing to the same instance name without raising registry collision exceptions.
2. **IPP Binary Protocol:** The server implements a minimal IPP 1.1 / 2.0 binary protocol parser, handling `Print-Job`, `Validate-Job`, and `Get-Printer-Attributes` operations. It responds with mandatory AirPrint capabilities (e.g., `airprint-1.8`, `media-ready`, `urf-supported`).
3. **Print Spooling:** When a document is received, it is dumped to a temporary file. `win32ui` and `win32print` are used in combination with `fitz` (PyMuPDF) to draw the document natively into the Windows print spooler.
