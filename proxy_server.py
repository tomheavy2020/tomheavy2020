import http.server
import socketserver
import urllib.request
import urllib.parse
import urllib.error
import os
import socket
import time # Keep this import

PORT = 9000

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path.startswith('/proxy/'):
            encoded_url_with_scheme = self.path[len('/proxy/'):]

            # Ensure the URL has a scheme for urllib.request
            if '://' not in encoded_url_with_scheme:
                target_url_str = 'http://' + urllib.parse.unquote(encoded_url_with_scheme)
            else:
                target_url_str = urllib.parse.unquote(encoded_url_with_scheme)

            print(f"Proxying request for: {target_url_str}")

            try:
                req = urllib.request.Request(target_url_str, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    content_type = response.headers.get('Content-Type', '').lower()
                    is_m3u8 = ('application/vnd.apple.mpegurl' in content_type or
                               'application/x-mpegurl' in content_type or
                               'audio/mpegurl' in content_type or
                               target_url_str.endswith('.m3u8'))

                    if is_m3u8:
                        print(f"M3U8 detected for: {target_url_str}")
                        m3u8_content = response.read().decode('utf-8', errors='ignore')
                        modified_m3u8_lines = []

                        # The base URL for resolving relative paths is the URL of the M3U8 file itself
                        base_m3u8_url = target_url_str

                        for line in m3u8_content.splitlines():
                            line_stripped = line.strip()
                            if line_stripped and not line_stripped.startswith('#'):
                                absolute_line_url = urllib.parse.urljoin(base_m3u8_url, line_stripped)

                                # Prepare target for proxying (remove scheme)
                                target_for_proxy = absolute_line_url
                                if target_for_proxy.startswith('http://'):
                                    target_for_proxy = target_for_proxy[len('http://'):]
                                elif target_for_proxy.startswith('https://'):
                                    target_for_proxy = target_for_proxy[len('https://'):]

                                encoded_target = urllib.parse.quote(target_for_proxy, safe='')
                                proxied_line = f"http://localhost:{PORT}/proxy/{encoded_target}"
                                modified_m3u8_lines.append(proxied_line)
                            else:
                                modified_m3u8_lines.append(line)

                        final_m3u8_output = "\n".join(modified_m3u8_lines)
                        final_m3u8_bytes = final_m3u8_output.encode('utf-8')

                        self.send_response(200)
                        # Send the original M3U8 content type if available, otherwise a common one
                        self.send_header('Content-Type', response.headers.get('Content-Type') or 'application/vnd.apple.mpegurl')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.send_header('Content-Length', str(len(final_m3u8_bytes)))
                        self.end_headers()
                        self.wfile.write(final_m3u8_bytes)
                        print(f"Finished sending modified M3U8 for: {target_url_str}")
                        return # Important: return after handling M3U8

                    else: # Not M3U8, stream directly
                        self.send_response(response.getcode()) # Use actual response code
                        # Send all original headers as received from the target server
                        for header, value in response.headers.items():
                             # Skip transfer-encoding if it's chunked, as we might change length
                            if header.lower() == 'transfer-encoding' and value.lower() == 'chunked':
                                continue
                            # Some servers might send a Content-Encoding we can't replicate (e.g. gzip if we altered content)
                            # For simplicity, we'll pass it through for now.
                            self.send_header(header, value)

                        # Ensure Access-Control-Allow-Origin is present
                        if 'Access-Control-Allow-Origin' not in response.headers:
                            self.send_header('Access-Control-Allow-Origin', '*')

                        # Content-Length might change if we modify content, but for direct proxy it's fine
                        # If 'Content-Length' is not in headers, it implies chunked or close.
                        # self.end_headers() should be called only once.
                        if not self.headers_sent: # Check if headers were already sent by send_header loop
                            self.end_headers()

                        # Stream the content
                        while True:
                            chunk = response.read(65536) # 64KB chunks
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush() # Ensure chunk is sent immediately
                        print(f"Finished streaming non-M3U8 content for: {target_url_str}")
                        return # Return after streaming

            except BrokenPipeError:
                print(f"Conexao interrompida pelo cliente (BrokenPipeError): {self.client_address} para o path {self.path}")
                # No further response to client, as pipe is broken
            except ConnectionResetError:
                print(f"Conexao resetada pelo cliente (ConnectionResetError): {self.client_address} para o path {self.path}")
                # No further response to client
            except urllib.error.HTTPError as e:
                # Use self.path for logging here as target_url_str might not be defined if error is early
                print(f"HTTPError: {e.code} - {e.reason} for Path: {self.path}, TargetURL: {target_url_str if 'target_url_str' in locals() else 'N/A'}")
                if not self.headers_sent:
                    self.send_response(e.code)
                    self.send_header('Content-Type', 'text/plain')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                self.wfile.write(f"HTTP Error {e.code}: {e.reason}".encode('utf-8'))
            except urllib.error.URLError as e:
                print(f"URLError: {e.reason} for Path: {self.path}, TargetURL: {target_url_str if 'target_url_str' in locals() else 'N/A'}")
                if not self.headers_sent:
                    self.send_response(502) # Bad Gateway
                    self.send_header('Content-Type', 'text/plain')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                self.wfile.write(f"URL Error: {e.reason}".encode('utf-8'))
            except socket.timeout:
                print(f"Timeout error for Path: {self.path}, TargetURL: {target_url_str if 'target_url_str' in locals() else 'N/A'}")
                if not self.headers_sent:
                    self.send_response(504)  # Gateway Timeout
                    self.send_header('Content-Type', 'text/plain')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                self.wfile.write(b"Gateway Timeout: The server took too long to respond.")
            except Exception as e:
                print(f"Erro geral no proxy para {self.path} (TargetURL: {target_url_str if 'target_url_str' in locals() else 'N/A'}): {type(e).__name__} - {str(e)}")
                if not self.headers_sent:
                    self.send_response(500)
                    self.send_header('Content-Type', 'text/plain')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                self.wfile.write(f"Internal Server Error: {type(e).__name__} - {str(e)}".encode('utf-8'))
            finally:
                # Make sure headers are ended if not already.
                # This can be tricky if an error occurs before self.end_headers() is called.
                # However, each path (success, HTTPError, URLError, Exception) calls end_headers().
                pass

        elif self.path == '/' or self.path.startswith('/index.html'):
            # Serve index.html for root or /index.html
            # This part assumes index.html is in the same directory as the script.
            # For a more robust solution, specify the directory or use a templating engine.
            try:
                # Try to find index.html in the current working directory
                # This might need adjustment if CWD is not where index.html is.
                # For now, assuming it's in the root of the project where proxy_server.py is.
                file_path = os.path.join(os.path.dirname(__file__), 'index.html')
                if not os.path.exists(file_path):
                     # Fallback to CWD if not found next to script (e.g. running from different dir)
                    file_path = 'index.html'

                with open(file_path, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    # Get file size for Content-Length
                    fs = os.fstat(f.fileno())
                    self.send_header('Content-Length', str(fs.st_size))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                print("index.html not found.")
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'index.html not found')
            except Exception as e:
                print(f"Error serving index.html: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Error serving index.html')
        else:
            # Fallback for other paths - you might want to serve other files or return 404
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'Resource not found')

    def do_POST(self):
        self.send_response(501)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"501 Not Implemented")

    # Keep serve_modified_m3u if it was intended to be part of this file,
    # otherwise it can be removed if not used by do_GET or do_POST.
    # For now, I'll assume it's not directly called by the new do_GET logic.
    # def serve_modified_m3u(self, content, base_url):
    #     pass # Placeholder

def run_server():
    # Ensure the server binds to a specific address to avoid OS choosing one randomly
    # especially in environments with multiple network interfaces.
    server_address = ('0.0.0.0', PORT) # Listen on all available interfaces

    # Attempt to create and bind the socket, with retries for "address already in use"
    max_retries = 5
    retry_delay = 2 # seconds

    for attempt in range(max_retries):
        try:
            httpd = socketserver.TCPServer(server_address, ProxyHTTPRequestHandler)
            print(f"Proxy server FINAŁŁŸ running on port {PORT}")
            httpd.serve_forever()
            break # Exit loop if server starts successfully
        except socket.error as e:
            if e.errno == socket.errno.EADDRINUSE:
                print(f"Port {PORT} is already in use. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                print(f"An unexpected socket error occurred: {e}")
                break # Exit on other socket errors
        except Exception as e:
            print(f"An unexpected error occurred while starting the server: {e}")
            break # Exit on other exceptions
    else:
        print(f"Failed to start server on port {PORT} after {max_retries} attempts. Please check if the port is available.")

if __name__ == '__main__':
    run_server()
