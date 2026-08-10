# AirPrint / IPP Bridge Server — Setup & Usage Guide

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | Ensure `python` and `pythonw.exe` are on `PATH` |
| **Windows 10 / 11** | Required for `pywin32` and the print spooler |
| **USB printer** | Must be set as the **default** Windows printer |
| **Same Wi‑Fi / LAN** | Mobile devices and the PC must share a subnet |

---

## 1 — Install Dependencies

```powershell
cd d:\Reports\Scripting\Antigravity\RemotePrintService
pip install -r requirements.txt
```

If `pywin32` post-install scripts haven't been run yet:

```powershell
python -m pywin32_postinstall -install
```

---

## 2 — Verify the Default Printer

```powershell
python -c "import win32print; print(win32print.GetDefaultPrinter())"
```

Make sure this returns the printer you want mobile devices to use.

---

## 3 — Quick Test (Foreground)

```powershell
python airprint_bridge.py
```

- The script logs to `airprint_bridge.log` in the same directory.
- On your iOS device, open any document → **Share → Print** — the PC's printer should appear.
- On Android, go to **Settings → Connected devices → Connection preferences → Printing → Default Print Service** and the printer should be listed.

> [!TIP]
> If the printer doesn't appear, check that Windows Firewall allows **inbound TCP port 631** and **mDNS (UDP 5353)**. See [Firewall rules](#4--firewall-rules) below.

---

## 4 — Firewall Rules

Run the following **once** from an elevated (Admin) PowerShell:

```powershell
# Allow IPP traffic on port 631
New-NetFirewallRule `
    -DisplayName "AirPrint Bridge - IPP (TCP 631)" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 631 `
    -Action Allow `
    -Profile Private

# Allow mDNS traffic (Zeroconf uses UDP 5353)
New-NetFirewallRule `
    -DisplayName "AirPrint Bridge - mDNS (UDP 5353)" `
    -Direction Inbound `
    -Protocol UDP `
    -LocalPort 5353 `
    -Action Allow `
    -Profile Private
```

---

## 5 — Silent Execution with `pythonw.exe`

`pythonw.exe` runs the script without any console window:

```powershell
pythonw.exe "d:\Reports\Scripting\Antigravity\RemotePrintService\airprint_bridge.py"
```

All output goes to `airprint_bridge.log` — no `print()` calls are used anywhere.

---

## 6 — Auto‑Start via Task Scheduler

1. Open **Task Scheduler** → **Create Task** (not "Basic Task").

2. **General** tab:
   - Name: `AirPrint Bridge`
   - Check **Run whether user is logged on or not**
   - Check **Run with highest privileges** (needed for port 631)

3. **Triggers** tab → **New…**
   - Begin the task: **At startup**
   - Optionally add a 30‑second delay to let Wi‑Fi connect first.

4. **Actions** tab → **New…**
   - Action: **Start a program**
   - Program/script:
     ```
     "C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\pythonw.exe"
     ```
     *(adjust to your actual `pythonw.exe` path)*
   - Add arguments:
     ```
     "d:\Reports\Scripting\Antigravity\RemotePrintService\airprint_bridge.py"
     ```
   - Start in:
     ```
     d:\Reports\Scripting\Antigravity\RemotePrintService
     ```

5. **Conditions** tab:
   - Uncheck **Start the task only if the computer is on AC power** (if using a laptop).

6. **Settings** tab:
   - Check **Allow task to be run on demand**
   - Check **If the task fails, restart every: 1 minute** (up to 3 times)
   - Set **Stop the task if it runs longer than:** to **Disabled** (it should run indefinitely)

7. Click **OK** and enter your Windows password when prompted.

---

## 7 — Managing the Running Service

| Action | Command |
|---|---|
| **View logs** | `Get-Content .\airprint_bridge.log -Tail 50 -Wait` |
| **Stop the service** | Task Scheduler → right-click → **End** |
| **Start the service** | Task Scheduler → right-click → **Run** |
| **Check if running** | `Get-Process pythonw \| Where-Object {$_.CommandLine -like '*airprint*'}` |

---

## Architecture Diagram

```
┌──────────────┐          mDNS (UDP 5353)          ┌───────────────────┐
│  iOS / Android│ ◄──────────────────────────────── │   Zeroconf        │
│  device       │                                   │   (DNS-SD advert) │
│               │ ── IPP Print-Job (TCP 631) ─────► │                   │
└──────────────┘                                   │   IPP HTTP Server │
                                                    │   (port 631)      │
                                                    │         │         │
                                                    │   Extract PDF/IMG │
                                                    │         │         │
                                                    │   ShellExecute    │
                                                    │   "printto" ──────┼──► Windows Print
                                                    │                   │    Spooler → USB
                                                    └───────────────────┘    Printer
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Printer not discovered | Confirm firewall rules (step 4). Verify device is on same subnet. |
| `WinError 10048: address in use` | Another process holds port 631. Check with `netstat -ano \| findstr :631`. |
| Job sent but nothing prints | Check `airprint_bridge.log` for spooling errors. Verify the default printer with step 2. |
| `ShellExecute` opens an app window | Some PDF viewers don't support silent `printto`. Install **SumatraPDF** (portable) — it handles `printto` headlessly. |
| Script crashes on startup | Run once with `python` (not `pythonw`) to see errors, or inspect the log file. |
