import http.server
import socketserver
import urllib.request
from urllib.parse import urlparse, urljoin

PORT = 8080
ALLOWED_DOMAINS = ["stream.zdf.de"]

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/proxy/"):
            self.handle_proxy_request()
        else:
            self.send_error(404, "File not found")

    def handle_proxy_request(self):
        target_url = self.path[len("/proxy/"):]
        parsed_url = urlparse(target_url)

        if parsed_url.hostname not in ALLOWED_DOMAINS:
            self.send_error(403, "Access forbidden: Domain not allowed")
            return

        try:
            with urllib.request.urlopen(target_url) as response:
                content_type = response.headers.get('Content-Type', 'application/octet-stream') # Added default
                is_m3u8 = "mpegurl" in content_type or target_url.endswith(".m3u8")

                if is_m3u8:
                    # For M3U8, process and rewrite URLs by streaming
                    # Headers will be sent by handle_m3u8_stream
                    self.handle_m3u8_stream(response, target_url, content_type)
                else:
                    # For other content types, read entire body and then write
                    response_body = response.read()
                    self.send_response(200)
                    self.send_header("Content-type", content_type)
                    self.send_header("Content-Length", str(len(response_body)))
                    self.end_headers()
                    self.wfile.write(response_body)

        except Exception as e:
            self.send_error(500, f"Error fetching URL: {e}")

    def handle_m3u8_stream(self, response_stream, base_url, content_type):
        # Processes M3U8 content line by line from the stream,
        # sends appropriate headers, and rewrites segment URLs.

        # Send headers for M3U8 stream
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        # DO NOT send Content-Length for streaming M3U8
        self.end_headers()

        # Process and write M3U8 lines
        for line_bytes in response_stream:
            line = line_bytes.decode('utf-8', errors='ignore').strip()
            if line and not line.startswith('#'):
                # This is a segment URL, rewrite it
                segment_url = urljoin(base_url, line)
                processed_lines.append(f"/proxy/{segment_url}")
            else:
                # This is a comment or directive, keep it as is
                self.wfile.write(line.encode('utf-8') + b'\n')
                continue # ensure only one write per line
            # This is a segment URL, rewrite it and write
            segment_url = urljoin(base_url, line)
            self.wfile.write(f"/proxy/{segment_url}".encode('utf-8') + b'\n')

    def log_message(self, format, *args):
        # Optional: Implement custom logging or suppress it
        return

if __name__ == '__main__':
    with socketserver.TCPServer(("", PORT), ProxyHandler) as httpd:
        print(f"Serving on port {PORT}")
        httpd.serve_forever()
