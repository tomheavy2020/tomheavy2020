#!/usr/bin/env python3
"""
HLS/M3U8 Streaming Proxy Server
Suporta arquivos M3U8 grandes com processamento eficiente em streaming
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import urllib.error
import logging
import re
import io
import time
from threading import Thread
from urllib.parse import urlparse, urljoin, quote
from http.client import HTTPResponse
from typing import Optional, Tuple, Dict

# Configurações
PORT = 8080
ALLOWED_DOMAINS = ["stream.zdf.de"]
CHUNK_SIZE = 64 * 1024  # 64KB chunks
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB max
CONNECTION_TIMEOUT = 30  # segundos
READ_TIMEOUT = 120  # segundos para arquivos grandes
BUFFER_SIZE = 8192  # Buffer para leitura linha por linha

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Regex para detectar URIs em tags HLS
HLS_URI_PATTERN = re.compile(
    r'(#EXT-X-[A-Z-]+:.*URI=")([^"]+)(")',
    re.IGNORECASE
)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Servidor HTTP com suporte a múltiplas threads"""
    daemon_threads = True
    request_queue_size = 100


class StreamingM3U8Processor:
    """Processa arquivos M3U8 grandes em modo streaming"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.line_count = 0
        self.bytes_processed = 0

    def process_line(self, line: str) -> str:
        """Processa uma linha do M3U8, reescrevendo URLs quando necessário"""
        self.line_count += 1

        if not line or line.startswith('#EXT'):
            # Processar tags com URIs (ex: #EXT-X-KEY:URI="...")
            def replace_uri(match):
                prefix, uri, suffix = match.groups()
                absolute_uri = urljoin(self.base_url, uri)
                proxied_uri = f"/proxy/{quote(absolute_uri, safe='/')}"
                logger.debug(f"Rewriting M3U8 URI: '{uri}' to '{proxied_uri}'") # Added line
                return f"{prefix}{proxied_uri}{suffix}"

            line = HLS_URI_PATTERN.sub(replace_uri, line)

        elif line and not line.startswith('#'):
            # É uma URL de segmento
            # It might also be beneficial to log segment URL rewriting
            original_segment_url = line.strip()
            segment_url = urljoin(self.base_url, original_segment_url)
            proxied_segment_url = f"/proxy/{quote(segment_url, safe='/')}"
            # Check if the line actually changed to avoid logging non-URL lines if any slip through
            if line != proxied_segment_url:
                 logger.debug(f"Rewriting M3U8 segment URL: '{original_segment_url}' to '{proxied_segment_url}'")
            line = proxied_segment_url

        return line


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Handler otimizado para proxy com suporte a streaming"""

    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        """Processa requisições GET"""
        try:
            if self.path.startswith("/proxy/"):
                self.handle_proxy_request()
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"Erro no handler: {e}", exc_info=True)
            if not self._headers_sent:
                self.send_error(500, "Internal Server Error")

    def do_HEAD(self):
        """Suporta requisições HEAD para compatibilidade com players"""
        self.do_GET()

    def handle_proxy_request(self):
        """Processa requisição de proxy com validação e streaming"""
        try:
            # Extrair e validar URL
            target_url = self.extract_target_url()
            if not target_url:
                return

            # Verificar domínio permitido
            if not self.is_domain_allowed(target_url):
                self.send_error(403, "Forbidden: Domain not allowed")
                return

            # Fazer requisição upstream
            request = self.create_upstream_request(target_url)

            with urllib.request.urlopen(request, timeout=CONNECTION_TIMEOUT) as response:
                # Detectar tipo de conteúdo
                content_type = response.headers.get('Content-Type', 'application/octet-stream')
                content_length = response.headers.get('Content-Length')

                # Verificar tamanho máximo
                if content_length and int(content_length) > MAX_FILE_SIZE:
                    self.send_error(413, "File too large")
                    return

                # Processar baseado no tipo
                if self.is_m3u8_content(content_type, target_url):
                    self.stream_m3u8_content(response, target_url, content_type)
                else:
                    self.stream_binary_content(response, content_type, content_length)

        except urllib.error.HTTPError as e:
            self.send_error(e.code, e.reason)
        except urllib.error.URLError as e:
            logger.error(f"Erro de conexão: {e}")
            self.send_error(504, "Gateway Timeout")
        except Exception as e:
            logger.error(f"Erro inesperado: {e}", exc_info=True)
            if not self._headers_sent:
                self.send_error(500, str(e))

    def extract_target_url(self) -> Optional[str]:
        """Extrai e valida a URL alvo do path"""
        try:
            # Remover /proxy/ e decodificar
            encoded_url = self.path[7:]  # len("/proxy/")
            target_url = urllib.parse.unquote(encoded_url)

            # Validar URL
            parsed = urlparse(target_url)
            if parsed.scheme not in ('http', 'https'):
                self.send_error(400, "Invalid URL scheme")
                return None

            return target_url

        except Exception as e:
            logger.error(f"Erro ao extrair URL: {e}")
            self.send_error(400, "Invalid URL")
            return None

    def is_domain_allowed(self, url: str) -> bool:
        """Verifica se o domínio é permitido com validação robusta"""
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False

        hostname = hostname.lower().strip('.')

        for allowed in ALLOWED_DOMAINS:
            allowed = allowed.lower().strip('.')
            if hostname == allowed or hostname.endswith(f".{allowed}"):
                return True

        return False

    def create_upstream_request(self, url: str) -> urllib.request.Request:
        """Cria requisição para o servidor upstream com headers apropriados"""
        headers = {
            'User-Agent': self.headers.get('User-Agent', 'Python-Proxy/1.0'),
            'Accept': self.headers.get('Accept', '*/*'),
            'Accept-Encoding': 'identity',  # Evitar compressão para simplificar
        }

        # Propagar alguns headers do cliente
        for header in ['Range', 'If-Modified-Since', 'If-None-Match']:
            if header in self.headers:
                headers[header] = self.headers[header]

        return urllib.request.Request(url, headers=headers)

    def is_m3u8_content(self, content_type: str, url: str) -> bool:
        """Detecta se o conteúdo é M3U8/HLS"""
        content_type = content_type.lower()
        return (
            'mpegurl' in content_type or
            'x-mpegurl' in content_type or
            url.lower().endswith(('.m3u8', '.m3u'))
        )

    def stream_m3u8_content(self, response: HTTPResponse, base_url: str, content_type: str):
        """Processa e transmite conteúdo M3U8 com eficiência para arquivos grandes"""
        logger.info(f"Processando M3U8: {base_url}")

        # Enviar headers com chunked encoding
        self._headers_sent = True
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Transfer-Encoding', 'chunked')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        # Processar M3U8 linha por linha
        processor = StreamingM3U8Processor(base_url)

        # Buffer para leitura eficiente
        buffer = io.BytesIO()
        total_bytes = 0
        start_time = time.time()

        try:
            while True:
                # Ler chunk do upstream
                chunk = response.read(BUFFER_SIZE)
                if not chunk:
                    # Processar última linha parcial se houver
                    if buffer.tell() > 0:
                        buffer.seek(0)
                        last_line = buffer.read().decode('utf-8', errors='ignore')
                        if last_line:
                            self._write_m3u8_line(processor.process_line(last_line))
                    break

                total_bytes += len(chunk)
                buffer.write(chunk)

                # Processar linhas completas do buffer
                buffer.seek(0)
                remaining = b''

                for line_bytes in buffer:
                    if line_bytes.endswith(b'\n'):
                        # Linha completa
                        line = line_bytes.decode('utf-8', errors='ignore').rstrip('\n')
                        processed = processor.process_line(line)
                        self._write_m3u8_line(processed)
                    else:
                        # Linha parcial, guardar para próxima iteração
                        remaining = line_bytes

                # Resetar buffer com linha parcial
                buffer = io.BytesIO()
                buffer.write(remaining)

                # Log de progresso para arquivos grandes
                if processor.line_count % 10000 == 0:
                    elapsed = time.time() - start_time
                    rate = total_bytes / elapsed / 1024 / 1024  # MB/s
                    logger.info(
                        f"M3U8 progress: {processor.line_count} lines, "
                        f"{total_bytes/1024/1024:.1f}MB, {rate:.1f}MB/s"
                    )

            # Finalizar chunked encoding
            self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()

            elapsed = time.time() - start_time
            logger.info(
                f"M3U8 completo: {processor.line_count} linhas, "
                f"{total_bytes/1024/1024:.1f}MB em {elapsed:.1f}s"
            )

        except (BrokenPipeError, ConnectionResetError) as e:
            logger.warning(f"Cliente desconectou durante streaming: {e}")
        except Exception as e:
            logger.error(f"Erro durante streaming M3U8: {e}", exc_info=True)

    def _write_m3u8_line(self, line: str):
        """Escreve uma linha processada no formato chunked"""
        data = (line + '\n').encode('utf-8')
        chunk_header = f'{len(data):X}\r\n'.encode('utf-8')

        self.wfile.write(chunk_header)
        self.wfile.write(data)
        self.wfile.write(b'\r\n')

    def stream_binary_content(self, response: HTTPResponse, content_type: str, content_length: Optional[str]):
        """Transmite conteúdo binário (não-M3U8) com streaming eficiente"""
        # Enviar headers
        self._headers_sent = True
        self.send_response(200)
        self.send_header('Content-Type', content_type)

        if content_length:
            self.send_header('Content-Length', content_length)
        else:
            self.send_header('Transfer-Encoding', 'chunked')

        # Propagar headers importantes
        for header in ['Cache-Control', 'ETag', 'Last-Modified', 'Accept-Ranges']:
            value = response.headers.get(header)
            if value:
                self.send_header(header, value)

        self.end_headers()

        # Stream do conteúdo
        bytes_sent = 0
        start_time = time.time()

        try:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break

                bytes_sent += len(chunk)

                if content_length:
                    # Envio direto
                    self.wfile.write(chunk)
                else:
                    # Envio chunked
                    self.wfile.write(f'{len(chunk):X}\r\n'.encode())
                    self.wfile.write(chunk)
                    self.wfile.write(b'\r\n')

                # Log de progresso para arquivos grandes
                if bytes_sent % (10 * 1024 * 1024) == 0:  # A cada 10MB
                    elapsed = time.time() - start_time
                    rate = bytes_sent / elapsed / 1024 / 1024
                    logger.info(f"Streaming: {bytes_sent/1024/1024:.1f}MB at {rate:.1f}MB/s")

            # Finalizar chunked se necessário
            if not content_length:
                self.wfile.write(b'0\r\n\r\n')

            self.wfile.flush()

            elapsed = time.time() - start_time
            logger.info(f"Streaming completo: {bytes_sent/1024/1024:.1f}MB em {elapsed:.1f}s")

        except (BrokenPipeError, ConnectionResetError) as e:
            logger.warning(f"Cliente desconectou: {e}")
        except Exception as e:
            logger.error(f"Erro durante streaming: {e}", exc_info=True)

    def log_message(self, format, *args):
        """Override para usar nosso logger"""
        logger.info(f"{self.client_address[0]} - {format % args}")

    def version_string(self):
        """Identificação do servidor"""
        return "HLS-Proxy/1.0"


class ProxyServer:
    """Classe principal do servidor proxy"""

    def __init__(self, port: int = PORT):
        self.port = port
        self.server = None

    def start(self):
        """Inicia o servidor proxy"""
        try:
            # Configurar servidor com reuso de endereço
            ThreadingHTTPServer.allow_reuse_address = True
            self.server = ThreadingHTTPServer(("", self.port), ProxyHandler)

            logger.info(f"Servidor proxy iniciado na porta {self.port}")
            logger.info(f"Domínios permitidos: {', '.join(ALLOWED_DOMAINS)}")
            logger.info(f"Tamanho máximo de arquivo: {MAX_FILE_SIZE/1024/1024:.0f}MB")
            logger.info("Pressione Ctrl+C para parar")

            # Servir requisições
            self.server.serve_forever()

        except KeyboardInterrupt:
            logger.info("Recebido sinal de parada...")
        except Exception as e:
            logger.error(f"Erro ao iniciar servidor: {e}", exc_info=True)
        finally:
            self.stop()

    def stop(self):
        """Para o servidor gracefully"""
        if self.server:
            logger.info("Parando servidor...")
            self.server.shutdown()
            self.server.server_close()
            logger.info("Servidor parado")


def main():
    """Função principal"""
    import argparse

    parser = argparse.ArgumentParser(description='HLS/M3U8 Streaming Proxy Server')
    parser.add_argument('-p', '--port', type=int, default=PORT,
                        help=f'Porta do servidor (padrão: {PORT})')
    parser.add_argument('-d', '--domain', action='append',
                        help='Domínio adicional permitido')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Modo verbose (debug logging)')

    args = parser.parse_args()

    # Configurar logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Adicionar domínios extras
    if args.domain:
        ALLOWED_DOMAINS.extend(args.domain)

    # Iniciar servidor
    server = ProxyServer(args.port)
    server.start()


if __name__ == '__main__':
    main()
