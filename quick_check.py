import http.client, struct, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = http.client.HTTPConnection('192.168.100.49', 631, timeout=5)
header = struct.pack('!BBHi', 2, 0, 0x000B, 99)
body = struct.pack('!B', 0x01)

def ta(t, n, v):
    nb = n.encode()
    vb = v.encode()
    return struct.pack('!B', t) + struct.pack('!H', len(nb)) + nb + struct.pack('!H', len(vb)) + vb

body += ta(0x47, 'attributes-charset', 'utf-8')
body += ta(0x48, 'attributes-natural-language', 'en-us')
body += ta(0x45, 'printer-uri', 'ipp://192.168.100.49:631/ipp/print')
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
