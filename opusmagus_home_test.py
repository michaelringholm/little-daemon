from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime

HOST = "0.0.0.0"
PORT = 7860

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        remote_ip = self.client_address[0]
        now = datetime.now().astimezone().isoformat(timespec="seconds")

        html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>OpusMagus Home Test</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background:#111; color:#eee;
           display:grid; place-items:center; min-height:100vh; margin:0; }}
    main {{ max-width:650px; padding:32px; }}
    h1 {{ margin-bottom:8px; }}
    code {{ color:#9fe870; }}
  </style>
</head>
<body>
<main>
  <h1>OpusMagus Home</h1>
  <p>If you can see this from outside your Wi-Fi, port forwarding works.</p>
  <p>Server: <code>{HOST}:{PORT}</code></p>
  <p>Your address as seen by this server: <code>{remote_ip}</code></p>
  <p>Time: <code>{now}</code></p>
</main>
</body>
</html>""".encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

if __name__ == "__main__":
    print(f"Listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
