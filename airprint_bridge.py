#!/usr/bin/env python3
"""
AirPrint / IPP Bridge Server for Windows
=========================================

Advertises a PC-connected USB printer on the local network via mDNS (DNS-SD)
so that iOS (AirPrint) and Android (IPP Everywhere) devices can discover and
print to it natively — no mobile apps required.

Architecture
------------
1. Zeroconf broadcasts ``_ipp._tcp.local.`` on the LAN.
2. A lightweight HTTP server on port 631 accepts IPP ``Print-Job`` requests.
3. The document payload (PDF / JPEG / PNG) is extracted from the binary IPP
   envelope and spooled to the default Windows printer via the Win32 API.

Author : Salman Asmat
Created: 2026-08-10
License: MIT
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import socket
import struct
import sys
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
try:
    from zeroconf import ServiceInfo, Zeroconf
except ImportError:
    raise SystemExit(
        "Missing dependency: zeroconf\n"
        "Install with:  pip install zeroconf"
    )

try:
    import win32api
    import win32print
except ImportError:
    raise SystemExit(
        "Missing dependency: pywin32\n"
        "Install with:  pip install pywin32"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IPP_PORT: int = 631
IPP_SERVICE_TYPE: str = "_ipp._tcp.local."

# IPP binary protocol constants
IPP_VERSION_MAJOR: int = 1
IPP_VERSION_MINOR: int = 1

# IPP operation IDs we handle
IPP_OP_PRINT_JOB: int = 0x0002
IPP_OP_VALIDATE_JOB: int = 0x0004
IPP_OP_GET_PRINTER_ATTRIBUTES: int = 0x000B
IPP_OP_GET_JOBS: int = 0x000A

# IPP status codes
IPP_STATUS_OK: int = 0x0000
IPP_STATUS_OK_IGNORED: int = 0x0001
IPP_STATUS_BAD_REQUEST: int = 0x0400
IPP_STATUS_NOT_FOUND: int = 0x0406
IPP_STATUS_INTERNAL_ERROR: int = 0x0500

# IPP attribute tags
IPP_TAG_OPERATION: int = 0x01
IPP_TAG_JOB: int = 0x02
IPP_TAG_END: int = 0x03
IPP_TAG_PRINTER: int = 0x04
IPP_TAG_UNSUPPORTED: int = 0x05

# IPP value tags
IPP_TAG_INTEGER: int = 0x21
IPP_TAG_BOOLEAN: int = 0x22
IPP_TAG_ENUM: int = 0x23
IPP_TAG_TEXT: int = 0x41
IPP_TAG_NAME: int = 0x42
IPP_TAG_KEYWORD: int = 0x44
IPP_TAG_URI: int = 0x45
IPP_TAG_URISCHEME: int = 0x46
IPP_TAG_CHARSET: int = 0x47
IPP_TAG_LANGUAGE: int = 0x48
IPP_TAG_MIMETYPE: int = 0x49
IPP_TAG_RANGE: int = 0x33

# File‑type magic bytes
MAGIC_PDF: bytes = b"%PDF"
MAGIC_JPEG: bytes = b"\xFF\xD8\xFF"
MAGIC_PNG: bytes = b"\x89PNG"
MAGIC_URF: bytes = b"UNIRAST"   # Apple Raster (URF) format

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
LOG_FILE: str = str(
    Path(__file__).resolve().parent / "airprint_bridge.log"
)

logger = logging.getLogger("airprint_bridge")
logger.setLevel(logging.DEBUG)

_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s  [%(levelname)-8s]  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
logger.addHandler(_file_handler)

# Prevent any output to stdout/stderr (headless-safe for pythonw.exe)
logging.getLogger().handlers = []


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    """Return the primary LAN IPv4 address of this machine."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually send data; used to determine the outbound iface.
        sock.connect(("8.8.8.8", 80))
        ip: str = sock.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        sock.close()
    logger.info("Detected local IP address: %s", ip)
    return ip


def detect_file_type(data: bytes) -> Tuple[str, str]:
    """
    Sniff the first few bytes of *data* and return ``(extension, mime_type)``.

    Falls back to ``('.bin', 'application/octet-stream')`` for unknown types.
    """
    if data[:4] == MAGIC_PDF:
        return ".pdf", "application/pdf"
    if data[:7] == MAGIC_URF:
        return ".urf", "image/urf"
    if data[:3] == MAGIC_JPEG:
        return ".jpg", "image/jpeg"
    if data[:4] == MAGIC_PNG:
        return ".png", "image/png"
    return ".bin", "application/octet-stream"


def convert_urf_to_pdf(urf_path: str) -> str:
    """
    Convert an Apple Raster (URF) file to PDF so Windows can print it.

    URF format: 'UNIRAST\x00' (8-byte header) followed by one or more
    page records.  Each page record has a 4-byte big-endian page header
    length, then pixel data.  We extract page images and compose them
    into a simple PDF.

    If the ``Pillow`` library is available, we decode the raster pages
    into images and wrap them in a PDF.  Otherwise, we fall back to
    writing raw bytes as a single-page PDF image.
    """
    pdf_path = urf_path.rsplit(".", 1)[0] + ".pdf"
    try:
        # Attempt conversion with Pillow (best quality)
        from PIL import Image
        import io

        with open(urf_path, "rb") as f:
            data = f.read()

        # URF header: 'UNIRAST\x00' (8 bytes) then page count (4 bytes BE)
        if len(data) < 12 or data[:8] != b"UNIRAST\x00":
            logger.warning("URF file has invalid header, treating as raw")
            return urf_path

        # Skip the 8-byte magic + 4-byte page count to the page data.
        # Each page has a 32-byte page header, then raw pixel data.
        # For a simpler approach, we try to find embedded JPEG or image data.
        offset = 12  # past magic + page count

        images = []
        while offset < len(data):
            # Page header is typically 32 bytes
            if offset + 32 > len(data):
                break
            # Bytes 16-19: width (BE), bytes 20-23: height (BE)
            # Byte 0: bits per pixel / color space info
            page_header = data[offset:offset + 32]
            bpp = page_header[0]  # bits per component
            color_space = page_header[1]  # 1=sGray, 3=sRGB
            # Duplex/quality fields at bytes 2,3
            width = struct.unpack("!I", page_header[16:20])[0]
            height = struct.unpack("!I", page_header[20:24])[0]
            # Resolution at bytes 8-11 (dpi)
            dpi = struct.unpack("!I", page_header[8:12])[0]
            if dpi == 0:
                dpi = 300

            offset += 32  # advance past page header

            # Determine channels and bytes per pixel
            if color_space == 1:
                channels = 1
                mode = "L"
            else:
                channels = 3
                mode = "RGB"

            row_bytes = width * channels
            page_data = bytearray()

            # URF uses a simple run-length encoding per row
            for _row in range(height):
                if offset >= len(data):
                    break
                row = bytearray()
                while len(row) < row_bytes:
                    if offset >= len(data):
                        break
                    count_byte = data[offset]
                    offset += 1
                    if count_byte == 0:
                        # Repeat the next pixel (count+1) times
                        # count_byte 0 = 1 repeat of next pixel
                        if offset + channels > len(data):
                            break
                        pixel = data[offset:offset + channels]
                        offset += channels
                        row.extend(pixel)
                    elif count_byte <= 127:
                        # Repeat next pixel (count_byte + 1) times
                        if offset + channels > len(data):
                            break
                        pixel = data[offset:offset + channels]
                        offset += channels
                        row.extend(pixel * (count_byte + 1))
                    else:
                        # (257 - count_byte) literal pixels follow
                        literal_count = 257 - count_byte
                        literal_bytes = literal_count * channels
                        if offset + literal_bytes > len(data):
                            break
                        row.extend(data[offset:offset + literal_bytes])
                        offset += literal_bytes
                # Pad or truncate to exact row width
                page_data.extend(row[:row_bytes])

            if width > 0 and height > 0 and len(page_data) >= row_bytes:
                actual_height = min(height, len(page_data) // row_bytes)
                img = Image.frombytes(
                    mode, (width, actual_height),
                    bytes(page_data[:actual_height * row_bytes]),
                )
                images.append(img)
                logger.info(
                    "URF page decoded: %dx%d %s @ %d dpi",
                    width, actual_height, mode, dpi,
                )

        if images:
            # Save all pages as a multi-page PDF
            first = images[0]
            if len(images) > 1:
                first.save(
                    pdf_path, "PDF", save_all=True,
                    append_images=images[1:], resolution=dpi,
                )
            else:
                first.save(pdf_path, "PDF", resolution=dpi)
            logger.info("URF converted to PDF: %s (%d pages)", pdf_path, len(images))
            return pdf_path

    except ImportError:
        logger.warning(
            "Pillow not installed — cannot convert URF to PDF. "
            "Install with: pip install Pillow"
        )
    except Exception:
        logger.exception("URF→PDF conversion failed")

    # Fallback: return original URF path (ShellExecute may still work
    # if the user has a URF-capable viewer installed)
    return urf_path


def get_default_printer() -> str:
    """Return the name of the Windows default printer."""
    name: str = win32print.GetDefaultPrinter()
    logger.info("Default Windows printer: %s", name)
    return name


def spool_to_printer(file_path: str, printer_name: str) -> None:
    """
    Send *file_path* to the Windows print queue of *printer_name*.

    Uses ``ShellExecute`` with the ``"printto"`` verb, which delegates
    rendering to whichever application is registered for the file type
    (e.g. Microsoft Print to PDF, Photos, SumatraPDF, etc.).
    """
    logger.info(
        "Spooling '%s' to printer '%s'", file_path, printer_name
    )
    try:
        win32api.ShellExecute(
            0,           # hWnd  – no parent window
            "printto",   # verb
            file_path,   # file to print
            f'"{printer_name}"',  # printer name (quoted for spaces)
            ".",         # working directory
            0,           # SW_HIDE – invisible window
        )
        logger.info("ShellExecute printto succeeded for '%s'", file_path)
    except Exception:
        logger.exception("ShellExecute printto FAILED for '%s'", file_path)
        raise


# ---------------------------------------------------------------------------
# IPP binary protocol helpers
# ---------------------------------------------------------------------------

def _encode_attribute(
    value_tag: int,
    name: str,
    value: bytes,
) -> bytes:
    """Encode a single IPP attribute into its binary wire format."""
    name_bytes = name.encode("ascii")
    return (
        struct.pack("!B", value_tag)
        + struct.pack("!H", len(name_bytes))
        + name_bytes
        + struct.pack("!H", len(value))
        + value
    )


def _encode_text_attribute(
    value_tag: int,
    name: str,
    text: str,
) -> bytes:
    """Convenience wrapper for text-valued attributes."""
    return _encode_attribute(value_tag, name, text.encode("utf-8"))


def _encode_integer_attribute(name: str, value: int) -> bytes:
    """Encode a 32-bit signed integer attribute."""
    return _encode_attribute(
        IPP_TAG_INTEGER, name, struct.pack("!i", value)
    )


def _encode_boolean_attribute(name: str, value: bool) -> bytes:
    """Encode a boolean attribute."""
    return _encode_attribute(
        IPP_TAG_BOOLEAN, name, struct.pack("!B", int(value))
    )


def _encode_enum_attribute(name: str, value: int) -> bytes:
    """Encode an enum (32-bit) attribute."""
    return _encode_attribute(
        IPP_TAG_ENUM, name, struct.pack("!i", value)
    )


def _encode_range_attribute(name: str, lower: int, upper: int) -> bytes:
    """Encode a rangeOfInteger attribute."""
    return _encode_attribute(
        IPP_TAG_RANGE, name, struct.pack("!ii", lower, upper)
    )


def _encode_additional_value(value_tag: int, value: bytes) -> bytes:
    """
    Encode an *additional value* for a multi-valued attribute.

    Per RFC 8011 §3.1.4 the name-length is 0 and no name follows.
    """
    return (
        struct.pack("!B", value_tag)
        + struct.pack("!H", 0)     # zero-length name
        + struct.pack("!H", len(value))
        + value
    )


def build_ipp_response(
    request_id: int,
    status_code: int,
    extra_groups: bytes = b"",
) -> bytes:
    """
    Assemble a minimal valid IPP response.

    Parameters
    ----------
    request_id : int
        Must echo the ``request-id`` from the client's request.
    status_code : int
        IPP status-code (``0x0000`` = successful-ok).
    extra_groups : bytes
        Pre-encoded attribute groups to append between the mandatory
        operation-attributes group and the end-of-attributes tag.
    """
    # ---- header (8 bytes) ----
    header = struct.pack(
        "!BBHi",
        IPP_VERSION_MAJOR,
        IPP_VERSION_MINOR,
        status_code,
        request_id,
    )

    # ---- mandatory operation attributes group ----
    body = struct.pack("!B", IPP_TAG_OPERATION)
    body += _encode_text_attribute(
        IPP_TAG_CHARSET, "attributes-charset", "utf-8"
    )
    body += _encode_text_attribute(
        IPP_TAG_LANGUAGE, "attributes-natural-language", "en-us"
    )

    # ---- optional extra attribute groups ----
    body += extra_groups

    # ---- end of attributes ----
    body += struct.pack("!B", IPP_TAG_END)

    return header + body


def parse_ipp_request(raw: bytes) -> Tuple[int, int, int]:
    """
    Parse the 8-byte IPP header.

    Returns ``(version_major << 8 | version_minor, operation_id, request_id)``.
    """
    if len(raw) < 8:
        raise ValueError("IPP payload too short (< 8 bytes)")
    ver_major, ver_minor, op_id, req_id = struct.unpack("!BBHi", raw[:8])
    return (ver_major << 8 | ver_minor), op_id, req_id


def extract_document_data(raw: bytes) -> bytes:
    """
    Locate the document payload inside a ``Print-Job`` request.

    The IPP spec says document data follows the *end-of-attributes-tag*
    (``0x03``).  We search for the tag that genuinely marks the boundary
    by walking through attribute groups properly.
    """
    # Walk through the IPP attributes to find the real end-of-attributes tag.
    # The header is 8 bytes; attributes start at offset 8.
    idx = 8
    while idx < len(raw):
        tag = raw[idx]
        idx += 1

        # Delimiter tags (0x00-0x05) — they occupy a single byte.
        if tag <= 0x05:
            if tag == IPP_TAG_END:
                # Everything after this byte is document data.
                return raw[idx:]
            # Other delimiter tags (operation, job, printer, …) — continue.
            continue

        # Value tag — followed by name-length(2) + name + value-length(2) + value
        if idx + 2 > len(raw):
            break
        name_len = struct.unpack("!H", raw[idx:idx + 2])[0]
        idx += 2 + name_len
        if idx + 2 > len(raw):
            break
        value_len = struct.unpack("!H", raw[idx:idx + 2])[0]
        idx += 2 + value_len

    # Fallback: brute-force scan for the end-of-attributes tag.
    # This handles edge cases with malformed attribute encodings.
    marker = raw.find(b"\x03", 8)
    if marker != -1:
        return raw[marker + 1:]

    return b""


# ---------------------------------------------------------------------------
# Build rich Get-Printer-Attributes response
# ---------------------------------------------------------------------------

def _build_printer_attributes(
    printer_name: str,
    host_ip: str,
) -> bytes:
    """
    Return the pre-encoded *printer-attributes* group that iOS / Android
    require in order to accept the printer as AirPrint-compatible.
    """
    printer_uri = f"ipp://{host_ip}:{IPP_PORT}/ipp/print"
    attrs = struct.pack("!B", IPP_TAG_PRINTER)

    # --- Identity ---
    attrs += _encode_text_attribute(IPP_TAG_URI, "printer-uri-supported", printer_uri)
    attrs += _encode_text_attribute(IPP_TAG_URISCHEME, "uri-security-supported", "none")
    attrs += _encode_text_attribute(IPP_TAG_URISCHEME, "uri-authentication-supported", "none")
    attrs += _encode_text_attribute(IPP_TAG_NAME, "printer-name", printer_name)
    attrs += _encode_text_attribute(IPP_TAG_TEXT, "printer-info", f"AirPrint Bridge – {printer_name}")
    attrs += _encode_text_attribute(IPP_TAG_TEXT, "printer-location", "Local Network")
    attrs += _encode_text_attribute(IPP_TAG_TEXT, "printer-make-and-model", "AirPrint Bridge Printer")

    # --- State ---
    # 3 = idle, 4 = processing, 5 = stopped
    attrs += _encode_enum_attribute("printer-state", 3)
    attrs += _encode_text_attribute(IPP_TAG_KEYWORD, "printer-state-reasons", "none")

    # --- Capabilities ---
    # iOS AirPrint requires image/urf in the supported formats list.
    attrs += _encode_text_attribute(IPP_TAG_MIMETYPE, "document-format-supported", "application/pdf")
    attrs += _encode_additional_value(IPP_TAG_MIMETYPE, b"image/urf")
    attrs += _encode_additional_value(IPP_TAG_MIMETYPE, b"image/jpeg")
    attrs += _encode_additional_value(IPP_TAG_MIMETYPE, b"image/png")
    attrs += _encode_additional_value(IPP_TAG_MIMETYPE, b"application/octet-stream")

    attrs += _encode_text_attribute(IPP_TAG_MIMETYPE, "document-format-default", "application/pdf")

    # Operations supported (Print-Job, Validate-Job, Get-Printer-Attributes, Get-Jobs)
    attrs += _encode_enum_attribute("operations-supported", IPP_OP_PRINT_JOB)
    attrs += _encode_additional_value(IPP_TAG_ENUM, struct.pack("!i", IPP_OP_VALIDATE_JOB))
    attrs += _encode_additional_value(IPP_TAG_ENUM, struct.pack("!i", IPP_OP_GET_PRINTER_ATTRIBUTES))
    attrs += _encode_additional_value(IPP_TAG_ENUM, struct.pack("!i", IPP_OP_GET_JOBS))

    # Charset & language
    attrs += _encode_text_attribute(IPP_TAG_CHARSET, "charset-configured", "utf-8")
    attrs += _encode_text_attribute(IPP_TAG_CHARSET, "charset-supported", "utf-8")
    attrs += _encode_text_attribute(IPP_TAG_LANGUAGE, "natural-language-configured", "en-us")
    attrs += _encode_text_attribute(IPP_TAG_LANGUAGE, "generated-natural-language-supported", "en-us")

    # Color support — MUST be boolean per IPP spec; iOS rejects keyword encoding.
    attrs += _encode_boolean_attribute("color-supported", False)

    # Pages-per-minute (informational)
    attrs += _encode_integer_attribute("pages-per-minute", 10)

    # Media & page size — 'iso_a4_210x297mm' + 'na_letter_8.5x11in'
    attrs += _encode_text_attribute(IPP_TAG_KEYWORD, "media-default", "iso_a4_210x297mm")
    attrs += _encode_text_attribute(IPP_TAG_KEYWORD, "media-supported", "iso_a4_210x297mm")
    attrs += _encode_additional_value(IPP_TAG_KEYWORD, b"na_letter_8.5x11in")

    # Sides (duplex) — we report simplex only for safety
    attrs += _encode_text_attribute(IPP_TAG_KEYWORD, "sides-default", "one-sided")
    attrs += _encode_text_attribute(IPP_TAG_KEYWORD, "sides-supported", "one-sided")

    # Copies
    attrs += _encode_range_attribute("copies-supported", 1, 99)
    attrs += _encode_integer_attribute("copies-default", 1)

    # IPP versions
    attrs += _encode_text_attribute(IPP_TAG_KEYWORD, "ipp-versions-supported", "1.1")
    attrs += _encode_additional_value(IPP_TAG_KEYWORD, b"2.0")

    # Multiple document handling
    attrs += _encode_text_attribute(
        IPP_TAG_KEYWORD,
        "multiple-document-jobs-supported",
        "false",
    )

    # Accepting jobs
    attrs += _encode_boolean_attribute("printer-is-accepting-jobs", True)

    # Number of queued jobs
    attrs += _encode_integer_attribute("queued-job-count", 0)

    # PDL override
    attrs += _encode_text_attribute(
        IPP_TAG_KEYWORD, "pdl-override-supported", "not-attempted"
    )

    # Compression
    attrs += _encode_text_attribute(IPP_TAG_KEYWORD, "compression-supported", "none")

    # Print quality
    attrs += _encode_enum_attribute("print-quality-default", 4)  # 4 = normal
    attrs += _encode_enum_attribute("print-quality-supported", 3)  # draft
    attrs += _encode_additional_value(IPP_TAG_ENUM, struct.pack("!i", 4))  # normal
    attrs += _encode_additional_value(IPP_TAG_ENUM, struct.pack("!i", 5))  # high

    # Printer UUID (deterministic from printer name)
    import hashlib
    uuid_hex = hashlib.md5(printer_name.encode()).hexdigest()
    printer_uuid = (
        f"urn:uuid:{uuid_hex[:8]}-{uuid_hex[8:12]}-"
        f"{uuid_hex[12:16]}-{uuid_hex[16:20]}-{uuid_hex[20:]}"
    )
    attrs += _encode_text_attribute(IPP_TAG_URI, "printer-uuid", printer_uuid)

    # printer-more-info — iOS checks for this URI
    attrs += _encode_text_attribute(
        IPP_TAG_URI, "printer-more-info",
        f"http://{host_ip}:{IPP_PORT}/",
    )

    # URF (Apple Raster) capabilities — iOS requires this attribute.
    # W8 = max width 8 inches, SRGB24 = 24-bit sRGB, V1.4 = URF version,
    # RS300-600 = supported resolutions, DM1 = duplex mode 1 (simplex).
    attrs += _encode_text_attribute(
        IPP_TAG_KEYWORD, "urf-supported", "W8"
    )
    attrs += _encode_additional_value(IPP_TAG_KEYWORD, b"SRGB24")
    attrs += _encode_additional_value(IPP_TAG_KEYWORD, b"V1.4")
    attrs += _encode_additional_value(IPP_TAG_KEYWORD, b"RS300-600")
    attrs += _encode_additional_value(IPP_TAG_KEYWORD, b"DM1")

    # AirPrint-specific: printer-type flags
    # Bit 0 = local, Bit 2 = can print — 0x05 covers the basics
    attrs += _encode_integer_attribute("printer-type", 0x00000005)

    return attrs


# ---------------------------------------------------------------------------
# IPP-aware HTTP request handler
# ---------------------------------------------------------------------------

class IPPRequestHandler(BaseHTTPRequestHandler):
    """
    Minimal HTTP handler that speaks enough IPP to satisfy AirPrint and
    Android's built-in IPP client.
    """

    # Reference to the Zeroconf-registered printer name (set on class).
    printer_name: str = ""
    host_ip: str = "127.0.0.1"

    # Silence the default stderr logging — we log to file.
    def log_message(self, fmt: str, *args: object) -> None:  # noqa: D401
        logger.info("HTTP  %s  %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------------ #
    # POST — the only verb iOS / Android use for IPP                      #
    # ------------------------------------------------------------------ #
    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_length)
        logger.info(
            "POST %s  Content-Length=%d  from %s",
            self.path,
            content_length,
            self.client_address[0],
        )

        if content_length < 8:
            self._send_ipp_error(0, IPP_STATUS_BAD_REQUEST)
            return

        try:
            _version, op_id, req_id = parse_ipp_request(raw)
        except ValueError as exc:
            logger.warning("Malformed IPP header: %s", exc)
            self._send_ipp_error(0, IPP_STATUS_BAD_REQUEST)
            return

        logger.info(
            "IPP operation=0x%04X  request-id=%d", op_id, req_id
        )

        if op_id == IPP_OP_PRINT_JOB:
            self._handle_print_job(raw, req_id)
        elif op_id == IPP_OP_VALIDATE_JOB:
            self._handle_validate_job(req_id)
        elif op_id == IPP_OP_GET_PRINTER_ATTRIBUTES:
            self._handle_get_printer_attributes(req_id)
        elif op_id == IPP_OP_GET_JOBS:
            self._handle_get_jobs(req_id)
        else:
            logger.warning("Unsupported IPP operation 0x%04X", op_id)
            self._send_ipp_error(req_id, IPP_STATUS_BAD_REQUEST)

    # ------------------------------------------------------------------ #
    # GET — some clients probe the root or /ipp/print via GET             #
    # ------------------------------------------------------------------ #
    def do_GET(self) -> None:  # noqa: N802
        logger.info(
            "GET %s  from %s", self.path, self.client_address[0]
        )
        # Return a simple human-readable status page.
        body = (
            "<html><body>"
            "<h1>AirPrint Bridge</h1>"
            f"<p>Printer: <strong>{self.printer_name}</strong></p>"
            "<p>IPP endpoint: <code>POST /ipp/print</code></p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------ #
    # IPP operation handlers                                              #
    # ------------------------------------------------------------------ #

    def _handle_print_job(self, raw: bytes, req_id: int) -> None:
        """Extract the document payload and spool it."""
        doc_data = extract_document_data(raw)
        if not doc_data:
            logger.error("No document data found in Print-Job payload")
            self._send_ipp_error(req_id, IPP_STATUS_BAD_REQUEST)
            return

        ext, mime = detect_file_type(doc_data)
        logger.info(
            "Document extracted: %d bytes, type=%s (%s)",
            len(doc_data),
            ext,
            mime,
        )

        # Write to a temp file
        tmp_dir = tempfile.gettempdir()
        tmp_path = os.path.join(
            tmp_dir, f"airprint_job_{req_id}{ext}"
        )
        try:
            with open(tmp_path, "wb") as fh:
                fh.write(doc_data)
            logger.info("Temp file written: %s", tmp_path)
        except OSError:
            logger.exception("Failed to write temp file")
            self._send_ipp_error(req_id, IPP_STATUS_INTERNAL_ERROR)
            return

        # Convert Apple Raster (URF) to PDF — Windows can't print URF natively.
        spool_path = tmp_path
        if ext == ".urf":
            spool_path = convert_urf_to_pdf(tmp_path)
            logger.info("Spool path after conversion: %s", spool_path)

        # Spool
        try:
            spool_to_printer(spool_path, self.printer_name)
        except Exception:
            logger.exception("Spooling failed")
            self._send_ipp_error(req_id, IPP_STATUS_INTERNAL_ERROR)
            return

        # Build a successful response with a job-attributes group
        job_attrs = struct.pack("!B", IPP_TAG_JOB)
        job_attrs += _encode_integer_attribute("job-id", req_id)
        job_attrs += _encode_text_attribute(
            IPP_TAG_URI,
            "job-uri",
            f"ipp://{self.host_ip}:{IPP_PORT}/ipp/print/job/{req_id}",
        )
        job_attrs += _encode_enum_attribute("job-state", 9)  # 9 = completed

        response = build_ipp_response(
            req_id, IPP_STATUS_OK, extra_groups=job_attrs
        )
        self._send_raw_ipp(response)
        logger.info("Print-Job #%d accepted and spooled successfully", req_id)

    def _handle_validate_job(self, req_id: int) -> None:
        """Respond to Validate-Job with successful-ok."""
        response = build_ipp_response(req_id, IPP_STATUS_OK)
        self._send_raw_ipp(response)
        logger.info("Validate-Job #%d → successful-ok", req_id)

    def _handle_get_printer_attributes(self, req_id: int) -> None:
        """Return a rich set of printer attributes for discovery."""
        attrs = _build_printer_attributes(self.printer_name, self.host_ip)
        response = build_ipp_response(
            req_id, IPP_STATUS_OK, extra_groups=attrs
        )
        self._send_raw_ipp(response)
        logger.info("Get-Printer-Attributes #%d → sent attributes", req_id)

    def _handle_get_jobs(self, req_id: int) -> None:
        """Return an empty job list (we don't queue)."""
        response = build_ipp_response(req_id, IPP_STATUS_OK)
        self._send_raw_ipp(response)
        logger.info("Get-Jobs #%d → empty list", req_id)

    # ------------------------------------------------------------------ #
    # Low-level response helpers                                          #
    # ------------------------------------------------------------------ #

    def _send_raw_ipp(self, data: bytes) -> None:
        """Send a raw IPP binary response over HTTP 200."""
        self.send_response(200)
        self.send_header("Content-Type", "application/ipp")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_ipp_error(self, req_id: int, status: int) -> None:
        """Send a minimal IPP error response."""
        response = build_ipp_response(req_id, status)
        self.send_response(200)  # IPP errors still ride on HTTP 200
        self.send_header("Content-Type", "application/ipp")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


# ---------------------------------------------------------------------------
# Threaded HTTP server wrapper
# ---------------------------------------------------------------------------

class ThreadedIPPServer(HTTPServer):
    """HTTPServer that handles each request in a new daemon thread."""

    allow_reuse_address = True
    daemon_threads = True

    def process_request(self, request, client_address) -> None:  # type: ignore[override]
        """Start a daemon thread for each incoming connection."""
        t = threading.Thread(
            target=self.process_request_thread,
            args=(request, client_address),
            daemon=True,
        )
        t.start()

    def process_request_thread(self, request, client_address) -> None:  # type: ignore[override]
        """Handle one request then close the socket."""
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


# ---------------------------------------------------------------------------
# mDNS / DNS-SD registration
# ---------------------------------------------------------------------------

class MDNSAdvertiser:
    """
    Registers (and later unregisters) an ``_ipp._tcp.local.`` service
    using the ``zeroconf`` library so that AirPrint / IPP Everywhere
    clients discover the printer automatically.

    Also registers the ``_universal._sub._ipp._tcp.local.`` subtype
    which iOS requires to classify the service as AirPrint-compatible.
    """

    def __init__(
        self,
        printer_name: str,
        host_ip: str,
        port: int = IPP_PORT,
    ) -> None:
        self._zc: Optional[Zeroconf] = None
        self._info: Optional[ServiceInfo] = None
        self._subtype_info: Optional[ServiceInfo] = None
        self._printer_name = printer_name
        self._host_ip = host_ip
        self._port = port

    def register(self) -> None:
        """Broadcast the service on the LAN."""
        # Sanitise the printer name for DNS labels (replace spaces, limit len)
        safe_name = (
            self._printer_name.replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")[:60]
        )
        service_name = f"{safe_name}.{IPP_SERVICE_TYPE}"

        # TXT record properties expected by AirPrint clients.
        # Key references:
        #   - Apple TN2078 (Bonjour Printing Specification)
        #   - RFC 8011 (IPP/2.0)
        txt_props = {
            "txtvers": "1",
            "qtotal": "1",
            "rp": "ipp/print",                   # resource path
            "ty": self._printer_name,             # human-readable type
            "product": "(AirPrint Bridge)",
            # iOS requires image/urf in the PDL list for AirPrint.
            "pdl": "application/pdf,image/urf,image/jpeg,image/png",
            "Color": "F",                         # F=monochrome, T=color
            "Duplex": "F",
            "adminurl": f"http://{self._host_ip}:{self._port}/",
            "priority": "50",
            # URF capability string — iOS silently drops printers with
            # URF=none.  Provide a minimal but valid capability set.
            "URF": "W8,SRGB24,V1.4,RS300-600,DM1",
            "TLS": "none",
        }

        # --- Primary service: _ipp._tcp.local. ---
        self._info = ServiceInfo(
            type_=IPP_SERVICE_TYPE,
            name=service_name,
            addresses=[socket.inet_aton(self._host_ip)],
            port=self._port,
            properties=txt_props,
            server=f"{safe_name}.local.",
        )

        self._zc = Zeroconf()
        self._zc.register_service(self._info, strict=False)
        logger.info(
            "mDNS service registered: %s  (IP=%s  port=%d)",
            service_name,
            self._host_ip,
            self._port,
        )

        # --- AirPrint subtype: _universal._sub._ipp._tcp.local. ---
        # iOS filters AirPrint printers by this DNS-SD subtype PTR record.
        # We register a second ServiceInfo with the subtype as type_ and
        # the same instance name — this creates the required PTR record.
        airprint_subtype = f"_universal._sub.{IPP_SERVICE_TYPE}"
        subtype_service_name = f"{safe_name}.{airprint_subtype}"

        self._subtype_info = ServiceInfo(
            type_=airprint_subtype,
            name=subtype_service_name,
            addresses=[socket.inet_aton(self._host_ip)],
            port=self._port,
            properties=txt_props,
            server=f"{safe_name}.local.",
        )
        try:
            self._zc.register_service(self._subtype_info, strict=False)
            logger.info(
                "mDNS subtype registered: %s", subtype_service_name
            )
        except Exception:
            # Non-fatal — Android will still work; only iOS may not.
            logger.exception(
                "Failed to register _universal subtype (AirPrint may "
                "not be visible on iOS)"
            )
            self._subtype_info = None

    def unregister(self) -> None:
        """Remove the service from the LAN."""
        if self._zc:
            logger.info("Unregistering mDNS service …")
            for info in (self._subtype_info, self._info):
                if info is not None:
                    try:
                        self._zc.unregister_service(info)
                    except Exception:
                        logger.exception(
                            "Error unregistering mDNS service: %s",
                            info.name if info else "unknown",
                        )
            try:
                self._zc.close()
            except Exception:
                logger.exception("Error closing Zeroconf")
            self._zc = None
            self._info = None
            self._subtype_info = None
            logger.info("mDNS service unregistered.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the AirPrint bridge server."""
    logger.info("=" * 60)
    logger.info("AirPrint Bridge starting up")
    logger.info("=" * 60)

    # ---- Detect environment ----
    host_ip = get_local_ip()
    printer_name = get_default_printer()
    if not printer_name:
        logger.critical("No default printer configured — aborting.")
        sys.exit(1)

    # ---- Configure the request handler class ----
    IPPRequestHandler.printer_name = printer_name
    IPPRequestHandler.host_ip = host_ip

    # ---- Start mDNS advertiser ----
    mdns = MDNSAdvertiser(printer_name, host_ip, IPP_PORT)
    mdns.register()

    # ---- Start HTTP / IPP server ----
    server = ThreadedIPPServer(("0.0.0.0", IPP_PORT), IPPRequestHandler)
    logger.info("IPP server listening on 0.0.0.0:%d", IPP_PORT)

    # ---- Graceful shutdown ----
    shutdown_event = threading.Event()

    def _shutdown(signum: Optional[int] = None, frame=None) -> None:
        """Signal handler — request a clean shutdown."""
        sig_name = (
            signal.Signals(signum).name if signum else "unknown"
        )
        logger.info("Shutdown requested (signal=%s)", sig_name)
        shutdown_event.set()

    # Register signal handlers for clean exit.
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    # On Windows, SIGBREAK covers Ctrl+Break and Task Manager termination.
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _shutdown)

    def _cleanup() -> None:
        """atexit hook — ensures mDNS is always unregistered."""
        mdns.unregister()
        logger.info("AirPrint Bridge shut down cleanly.")

    atexit.register(_cleanup)

    # Run the server in a background thread so we can wait on the event.
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    logger.info("Server thread started — ready to accept print jobs.")

    try:
        # Block the main thread until a shutdown signal fires.
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt caught — shutting down …")
    finally:
        server.shutdown()
        _cleanup()


if __name__ == "__main__":
    main()
