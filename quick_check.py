import http.client, struct, sys, socket
sys.stdout.reconfigure(encoding='utf-8')

# Accept host from CLI, or auto-detect local IP
if len(sys.argv) >= 2:
    HOST = sys.argv[1]
else:
    _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _sock.connect(("8.8.8.8", 80))
        HOST = _sock.getsockname()[0]
    except OSError:
        HOST = "127.0.0.1"
    finally:
        _sock.close()

PORT = int(sys.argv[2]) if len(sys.argv) >= 3 else 631
print(f"Target: {HOST}:{PORT}")

conn = http.client.HTTPConnection(HOST, PORT, timeout=5)
header = struct.pack('!BBHi', 2, 0, 0x000B, 99)
body = struct.pack('!B', 0x01)

def encode_text_attr(tag, name, value):
    """Encode an IPP text attribute into binary format."""
    nb = name.encode()
    vb = value.encode()
    return struct.pack('!B', tag) + struct.pack('!H', len(nb)) + nb + struct.pack('!H', len(vb)) + vb

body += encode_text_attr(0x47, 'attributes-charset', 'utf-8')
body += encode_text_attr(0x48, 'attributes-natural-language', 'en-us')
body += encode_text_attr(0x45, 'printer-uri', f'ipp://{HOST}:{PORT}/ipp/print')
body += struct.pack('!B', 0x03)

conn.request('POST', '/ipp/print', body=header + body, headers={'Content-Type': 'application/ipp'})
data = conn.getresponse().read()

print(f'Response IPP version: {data[0]}.{data[1]}')
print(f'Response size: {len(data)} bytes')

for attr in [b'ipp-features-supported', b'airprint-1.8', b'media-ready', b'media-col-supported']:
    found = attr in data
    label = 'YES' if found else 'NO '
    print(f'  {label}: {attr.decode()}')

conn.close()
