# Social Media Announcements — v1.2.0

## LinkedIn Post

Printing from mobile devices directly to any PC-connected printer without third-party apps just got even better.

I'm excited to announce Windows AirPrint Bridge v1.2.0! 🚀

While iOS (AirPrint) support has been seamless, Android devices running the Default Print Service (IPP Everywhere / Mopria standard) occasionally struggled to discover bridge-hosted printers. In this release, we completely resolved this by aligning our mDNS TXT record UUID generation with IPP response attributes, strictly adhering to RFC 8011 tag standards, and expanding support for PWG-Raster formats.

Now, both iOS and Android devices on the same Wi-Fi network can discover and print natively to any USB/local printer on Windows with zero mobile apps required.

Key Updates in v1.2.0:
- Full Native Android Discovery: Strict UUID synchronization between mDNS and IPP headers.
- RFC 8011 Compliance: Proper IPP keyword attribute tag formatting.
- Expanded PDL Support: Added image/pwg-raster support for Android/Mopria clients.
- Automated Windows Installer: Clean setup wizard running as a background Windows Service.

Check out the open-source release and standalone installer on GitHub:
https://github.com/salmanasmat/Windows-AirPrint-Bridge/releases/latest

#OpenSource #Python #Windows #AirPrint #Android #DevCommunity #SoftwareEngineering

---

## Reddit Post

**Target Subreddits:** r/selfhosted, r/sysadmin, r/windows, r/androidapps, r/opensource

**Title:** Windows AirPrint Bridge v1.2.0: Native driverless printing for both iOS (AirPrint) and Android (IPP Everywhere) from any PC-connected printer

**Post Content:**

Hey everyone,

A common headache with older or USB-only printers connected to a Windows PC is sharing them seamlessly to smartphones without installing proprietary manufacturer apps.

I built **Windows AirPrint Bridge** — a standalone, zero-config Python bridge that turns any Windows printer into a native AirPrint and IPP Everywhere network printer.

We just released **v1.2.0**, bringing **full native Android compatibility** alongside existing iOS AirPrint support!

### What's New in v1.2.0:
- **Android BIPS Discovery Fix:** Solved the issue where Android's Default Print Service (com.android.bips) discarded printers due to UUID discrepancies between mDNS TXT records and IPP Get-Printer-Attributes payloads.
- **RFC 8011 Attribute Encoding:** Updated authentication and security attribute tags to strictly match IPP specs.
- **PWG-Raster PDL Support:** Added image/pwg-raster to supported format headers.
- **Background Windows Service:** Bundled as an automated Inno Setup wizard that installs and manages the background service automatically.

### How it works:
1. Broadcasts mDNS _ipp._tcp and _universal._sub._ipp._tcp on your local network.
2. Accepts standard binary IPP Print-Job requests on port 631.
3. Renders PDF/URF/image payloads headlessly and spools directly to your default Windows printer via Win32 DC APIs.

Project link & pre-built installer:
https://github.com/salmanasmat/Windows-AirPrint-Bridge

Feedback and bug reports are welcome!

---

## X (Twitter) Post

Windows AirPrint Bridge v1.2.0 is out! 🚀

Print natively to any PC-connected printer from both iOS & Android with ZERO mobile apps.

✨ Native Android (IPP Everywhere) discovery fixed
✨ RFC 8011 tag compliance
✨ Background Windows Service installer

Get it: https://github.com/salmanasmat/Windows-AirPrint-Bridge
