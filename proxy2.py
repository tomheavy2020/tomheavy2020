import http.server
import socketserver
import urllib.request
from urllib.parse import urlparse, unquote, urljoin
import os
import mimetypes # For determining content type of index.html related assets

PORT = 9000
INDEX_HTML_PATH = 'index.html' # Default, can be relative to script or CWD
# Try to find index.html next to the script first, then in CWD
PROBE_PATHS = [
    os.path.join(os.path.dirname(__file__), INDEX_HTML_PATH),
    INDEX_HTML_PATH
]

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    # Store the resolved path to index.html to avoid probing on every request
    resolved_index_html_path = None

    def __init__(self, *args, **kwargs):
        # Determine the actual path for index.html once
        if ProxyHTTPRequestHandler.resolved_index_html_path is None:
            for path_to_try in PROBE_PATHS:
                if os.path.exists(path_to_try):
                    ProxyHTTPRequestHandler.resolved_index_html_path = os.path.abspath(path_to_try)
                    # Removed print statement for found path
                    break
            if ProxyHTTPRequestHandler.resolved_index_html_path is None:
                # Removed print statement for warning if not found
                pass

        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Serve a GET request by either proxying or serving local files."""
        if self.path.startswith('/proxy/'):
            self.handle_proxy_request()
        elif self.path == '/' or self.path.startswith('/index.html'):
            self.serve_index_html_or_asset()
        elif self.path == '/basic.m3u': # Example: serve basic.m3u directly
             try:
                # Assuming basic.m3u is in the same directory as this script or CWD
                # Prioritize script directory
                m3u_path_script_dir = os.path.join(os.path.dirname(__file__), 'basic.m3u')
                m3u_path_cwd = 'basic.m3u'
                actual_m3u_path = None

                if os.path.exists(m3u_path_script_dir):
                    actual_m3u_path = m3u_path_script_dir
                elif os.path.exists(m3u_path_cwd):
                    actual_m3u_path = m3u_path_cwd

                if actual_m3u_path:
                    with open(actual_m3u_path, 'rb') as f:
                        self.send_response(200)
                        self.send_header('Content-type', 'application/vnd.apple.mpegurl') # M3U8 type
                        self.end_headers()
                        self.wfile.write(f.read())
                    print(f"Served local basic.m3u from {actual_m3u_path}")
                else:
                    self.send_error_response(404, "basic.m3u not found.")
                    print("basic.m3u not found in script directory or CWD.")

             except Exception as e:
                self.send_error_response(500, f"Error serving basic.m3u: {e}")
                print(f"Error serving basic.m3u: {e}")
        else:
            # Fallback to serving files from the directory if not a proxy or special path
            # This allows serving CSS/JS files referenced by index.html if they are in the same dir
            # However, this current implementation of SimpleHTTPRequestHandler serves from CWD.
            # For serving relative to script dir, more work is needed in SimpleHTTPRequestHandler or by subclassing.
            # For now, ensure CWD is where your assets are, or use absolute paths in index.html, or use a more advanced static server.
            print(f"Attempting to serve static file: {self.path} from CWD: {os.getcwd()}")
            super().do_GET()


    def handle_proxy_request(self):
        target_url_encoded = self.path[len('/proxy/'):]
        target_url = unquote(target_url_encoded)

        if not target_url.startswith('http://') and not target_url.startswith('https://'):
            self.send_error_response(400, "Target URL must be absolute (start with http:// or https://)")
            return

        print(f"Proxying: {target_url}")
        is_m3u8 = target_url.endswith('.m3u8') or "m3u8" in target_url.lower() # Basic check

        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "ProxyHTTPRequestHandler/1.0"})
            with urllib.request.urlopen(req, timeout=20) as response: # Increased timeout
                response_body = response.read()
                content_type = response.headers.get('Content-Type', 'application/octet-stream')

                if is_m3u8:
                    self.handle_m3u8(response_body, target_url, content_type)
                else:
                    self.handle_regular_stream(response_body, response.getcode(), response.headers)

            print(f"Successfully proxied and processed: {target_url} - Status: {response.getcode()}")

        except urllib.error.HTTPError as e:
            self.send_error_response(e.code, f"HTTPError from target: {e.reason}")
            print(f"HTTPError proxying {target_url}: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            self.send_error_response(504, f"URLError (e.g., timeout, host not found): {e.reason}")
            print(f"URLError proxying {target_url}: {e.reason}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected proxy error: {e}")
            print(f"Unexpected error proxying {target_url}: {e}")


    def handle_m3u8(self, m3u8_content, base_url, content_type):
        """Processes M3U8 content to prepend proxy path to segment URLs."""
        lines = m3u8_content.decode('utf-8').splitlines()
        processed_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # This is a URL, prepend the proxy path
                # Ensure the segment URL is absolute
                segment_url = urljoin(base_url, line)
                processed_lines.append(f"/proxy/{segment_url}")
            else:
                processed_lines.append(line)

        processed_m3u8 = "\n".join(processed_lines).encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', content_type) # Use original or M3U8 specific
        self.send_header('Content-Length', str(len(processed_m3u8)))
        self.end_headers()
        self.wfile.write(processed_m3u8)
        print(f"Processed and served M3U8 from: {base_url}")

    def handle_regular_stream(self, body, status_code, headers):
        """Handles regular stream data by forwarding it."""
        self.send_response(status_code)
        for header, value in headers.items():
            if header.lower() not in ['transfer-encoding', 'connection', 'content-encoding', 'server']:
                self.send_header(header, value)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(message.encode('utf-8'))
        # Overriding log_error or send_error could also customize error logging
        # For now, explicit print for errors is in handle_proxy_request

    def serve_index_html_or_asset(self):
        """Serves index.html or other assets like CSS/JS from specified locations."""
        # Determine if it's index.html or another asset (e.g. CSS, JS)
        # For simplicity, this example focuses on index.html.
        # A more robust solution would check the path and serve other assets too.
        # This example assumes index.html and its assets are in the same directory.

        path_to_serve = self.path.lstrip('/') # e.g. "index.html" or "styles.css"
        if not path_to_serve or path_to_serve == 'index.html': # Root path or explicit index.html
            target_file_path = ProxyHTTPRequestHandler.resolved_index_html_path
        else:
            # Attempt to serve other assets relative to the index.html location or CWD
            # This is a simplification. For robust static serving, directory needs to be set for SimpleHTTPRequestHandler
            # or handle file reading manually.
            base_dir = os.path.dirname(ProxyHTTPRequestHandler.resolved_index_html_path) if ProxyHTTPRequestHandler.resolved_index_html_path else os.getcwd()
            target_file_path = os.path.join(base_dir, path_to_serve)
            target_file_path = os.path.abspath(target_file_path) # Ensure it's an absolute path

            # Security: Ensure the target_file_path is still within an expected directory
            # This is a basic check; a real server would need more robust path traversal protection.
            if not target_file_path.startswith(os.path.abspath(base_dir)):
                self.send_error_response(403, "Forbidden: Access to this path is not allowed.")
                print(f"Forbidden access attempt to: {target_file_path}")
                return


        if target_file_path and os.path.exists(target_file_path) and os.path.isfile(target_file_path):
            try:
                with open(target_file_path, 'rb') as f:
                    self.send_response(200)
                    # Guess content type
                    content_type, _ = mimetypes.guess_type(target_file_path)
                    if content_type:
                        self.send_header('Content-type', content_type)
                    else:
                        self.send_header('Content-type', 'application/octet-stream') # Default
                    fs = os.fstat(f.fileno())
                    self.send_header("Content-Length", str(fs[6]))
                    self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                    self.end_headers()
                    self.wfile.write(f.read())
                print(f"Served: {target_file_path}")
            except Exception as e:
                error_message = f"Error reading or serving file {target_file_path}: {e}"
                print(error_message)
                self.send_error_response(500, error_message)
        else:
            if self.path == '/' or self.path.startswith('/index.html'): # Specifically for index.html
                # Construct the paths it tried for a more informative error message
                script_dir_probe = os.path.join(os.path.dirname(__file__), INDEX_HTML_PATH)
                cwd_probe = INDEX_HTML_PATH # Relative to where the script is run
                error_message_detail = (
                    f"{INDEX_HTML_PATH} not found. Probed locations:\n"
                    f"1. Resolved path: {ProxyHTTPRequestHandler.resolved_index_html_path or 'None (not found during init)'}\n"
                    f"2. Script directory probe: {os.path.abspath(script_dir_probe)}\n"
                    f"3. Current working directory probe: {os.path.abspath(cwd_probe)}"
                )
                print(f"Error serving index.html: {error_message_detail}")
                self.send_error_response(404, error_message_detail)
            else: # For other assets not found
                self.send_error_response(404, f"File not found: {self.path.lstrip('/')}")
                print(f"Asset not found: {target_file_path}")

    def log_message(self, format, *args):
        """Override to customize logging or suppress it."""
        # To suppress logging:
        # return
        # Default logging:
        super().log_message(format, *args)


def run_server(server_class=http.server.ThreadingHTTPServer, handler_class=ProxyHTTPRequestHandler, port=PORT):
    # ThreadingHTTPServer handles each request in a new thread
    server_address = ('0.0.0.0', port) # Listen on all available IPs
    httpd = server_class(server_address, handler_class)
    print(f"Starting M3U Proxy and HTTP server on port {port}...")
    print(f"  Proxy endpoint: http://localhost:{port}/proxy/YOUR_TARGET_URL")
    print(f"  HTML player: http://localhost:{port}/")

    if handler_class.resolved_index_html_path: # Use handler_class as per the request
        print(f"  Serving index.html from: {handler_class.resolved_index_html_path}")
    else:
        print(f"  Warning: index.html could not be found. Player interface may not be available.")
        # Construct the probed paths string for the warning message
        probed_paths_str = ", ".join([os.path.abspath(p) for p in PROBE_PATHS])
        print(f"  Searched in: [{probed_paths_str}]")

    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
