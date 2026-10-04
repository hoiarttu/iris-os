"""
companion_server.py — IRIS phone companion (minimal: location relay only)
─────────────────────────────────────────────────────────────────────────────
Standalone, like hand_tracker.py — run separately, not wired into main.py.
Serves a one-page phone UI over HTTPS. Phone taps a button, sends its GPS
position once; this writes last_location.json, which DashApp's WeatherReader
already reads from.

Phone: browse to https://<pi-ip>:8443  (Safari will warn once — allow it)
"""

import http.server
import ssl
import json
import pathlib

PORT          = 8443
CERT_FILE     = 'cert.pem'
KEY_FILE      = 'key.pem'
LOCATION_PATH = 'last_location.json'

PAGE = b"""<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>IRIS</title>
<style>
  body { background:#000; color:#fff; font-family:sans-serif; text-align:center; padding-top:40vh; }
  button { font-size:1.4em; padding:0.8em 1.6em; background:#50dcff; border:none; border-radius:12px; }
  #status { margin-top:1.5em; color:#888; }
</style></head>
<body>
  <button onclick="send()">Send location to IRIS</button>
  <div id="status"></div>
<script>
function send() {
  const s = document.getElementById('status');
  s.textContent = 'Locating...';
  navigator.geolocation.getCurrentPosition(
    pos => {
      fetch('/location', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({lat: pos.coords.latitude, lon: pos.coords.longitude})
      }).then(() => s.textContent = 'Sent.')
        .catch(() => s.textContent = 'Failed to reach IRIS.');
    },
    err => { s.textContent = 'Location error: ' + err.message; },
    {enableHighAccuracy: true, timeout: 10000}
  );
}
</script>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(PAGE)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != '/location':
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            data   = json.loads(self.rfile.read(length))
            lat, lon = float(data['lat']), float(data['lon'])
            pathlib.Path(LOCATION_PATH).write_text(
                json.dumps({'lat': lat, 'lon': lon}))
            print(f'[Companion] Location received: {lat:.4f}, {lon:.4f}')
            self.send_response(200)
            self.end_headers()
        except Exception as e:
            print(f'[Companion] Bad location POST: {e}')
            self.send_response(400)
            self.end_headers()


def main():
    httpd = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f'[Companion] Serving on https://0.0.0.0:{PORT}')
    httpd.serve_forever()


if __name__ == '__main__':
    main()
