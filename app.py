from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import urllib.parse # For quote and unquote

app = FastAPI()

# CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permite todas as origens
    allow_credentials=True,
    allow_methods=["*"], # Permite todos os métodos (GET, POST, etc.)
    allow_headers=["*"], # Permite todos os cabeçalhos
)

# Diretório para armazenar listas M3U, se necessário
PLAYLISTS_DIR = "playlists"
if not os.path.exists(PLAYLISTS_DIR):
    os.makedirs(PLAYLISTS_DIR)

# Exemplo de conteúdo para um arquivo M3U de teste (exemplo.m3u)
sample_m3u_content = """#EXTM3U
#EXTINF:-1 tvg-id="channel1" tvg-name="Channel 1" group-title="News",Channel 1
http://example.com/stream1.m3u8
#EXTINF:-1 tvg-id="channel2" tvg-name="Channel 2" group-title="Sports",Channel 2
https://another.example.com/live/stream2.ts
#EXTINF:-1, Channel 3 - No extra attributes
http://third.example.com/video/playlist.m3u8
"""
with open(os.path.join(PLAYLISTS_DIR, "exemplo.m3u"), "w") as f:
    f.write(sample_m3u_content)


@app.get("/{m3u_file}")
async def serve_m3u(m3u_file: str):
    if not m3u_file.endswith('.m3u'):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou tipo inválido")

    try:
        # Buscar o arquivo da pasta 'playlists'
        file_path = os.path.join(PLAYLISTS_DIR, m3u_file)

        # Sanitize m3u_file to prevent path traversal
        if ".." in m3u_file or m3u_file.startswith("/"):
             raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")


        if not os.path.exists(file_path):
            # Try case-insensitive match as a fallback for some systems/users
            found_file = None
            for f_name in os.listdir(PLAYLISTS_DIR):
                if f_name.lower() == m3u_file.lower():
                    if f_name.endswith('.m3u'): # Double check extension
                        file_path = os.path.join(PLAYLISTS_DIR, f_name)
                        found_file = True
                        break
            if not found_file:
                raise HTTPException(status_code=404, detail=f"Arquivo '{m3u_file}' não encontrado em '{PLAYLISTS_DIR}'. Verifique o nome e a localização.")

        # Lê o conteúdo do arquivo
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        lines = content.splitlines()
        modified_lines = []
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith("http://") or stripped_line.startswith("https://"):
                encoded_original_url = urllib.parse.quote(stripped_line, safe='')
                # Assuming the FastAPI app itself is serving on port 9000 as per uvicorn.run
                proxied_url = f"http://localhost:9000/proxy/{encoded_original_url}"
                modified_lines.append(proxied_url)
            else:
                modified_lines.append(line) # Keep original line formatting (not stripped)

        modified_content = "\n".join(modified_lines)

        # Retorna o conteúdo modificado com o media type correto para M3U8
        return Response(content=modified_content, media_type="application/vnd.apple.mpegurl")

    except HTTPException:
        raise # Re-raise HTTPException to preserve status code and detail
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo '{m3u_file}': {str(e)}")


# Proxy endpoint
@app.get("/proxy/{encoded_url:path}")
async def proxy_stream(encoded_url: str, request: Request):
    try:
        # Decodifica a URL original
        original_url = urllib.parse.unquote(encoded_url)

        # Adiciona o esquema se não estiver presente (necessário para httpx)
        if not original_url.startswith("http://") and not original_url.startswith("https://"):
            original_url = "http://" + original_url

        async with httpx.AsyncClient(timeout=30.0) as client: # Timeout aumentado
            # Monta a requisição para o servidor de destino
            # Passa adiante os headers relevantes da requisição original
            headers_to_forward = {
                "User-Agent": request.headers.get("User-Agent", "FastAPI-Proxy/1.0"),
                "Accept": request.headers.get("Accept", "*/*"),
                "Range": request.headers.get("Range", None), # Importante para streaming/VOD
                # Adicione outros headers que você considera importantes
            }
            # Remove headers None
            headers_to_forward = {k: v for k, v in headers_to_forward.items() if v is not None}

            rp_req = client.build_request(
                method=request.method,
                url=original_url,
                headers=headers_to_forward,
                # O conteúdo da requisição (POST body) não é passado neste GET proxy simples
            )

            # Faz a requisição ao servidor de destino
            rp_resp = await client.send(rp_req, stream=True)
            rp_resp.raise_for_status() # Levanta exceção para respostas 4xx/5xx

            content_type = rp_resp.headers.get('Content-Type', '').lower()
            is_m3u8 = ('application/vnd.apple.mpegurl' in content_type or
                       'application/x-mpegurl' in content_type or
                       'audio/mpegurl' in content_type or
                       original_url.endswith('.m3u8'))

            if is_m3u8:
                m3u8_content_bytes = await rp_resp.aread()
                await rp_resp.aclose() # Fecha a resposta original, já que lemos tudo
                m3u8_content_str = m3u8_content_bytes.decode('utf-8', errors='ignore')

                modified_lines = []
                # original_url é a URL base do M3U8 que acabamos de buscar
                for line in m3u8_content_str.splitlines():
                    stripped_line = line.strip()
                    if stripped_line and not stripped_line.startswith('#'):
                        absolute_line_url = urllib.parse.urljoin(original_url, stripped_line)
                        encoded_target_url = urllib.parse.quote(absolute_line_url, safe='')
                        # Assume que o FastAPI está rodando em localhost:9000
                        proxied_segment_url = f"http://localhost:9000/proxy/{encoded_target_url}"
                        modified_lines.append(proxied_segment_url)
                    else:
                        modified_lines.append(line)

                final_m3u8_output = "\n".join(modified_lines)

                # Headers para a resposta M3U8 modificada
                response_m3u8_headers = {
                    "Content-Type": rp_resp.headers.get('Content-Type', 'application/vnd.apple.mpegurl'),
                    "Access-Control-Allow-Origin": "*",
                    "Content-Length": str(len(final_m3u8_output.encode('utf-8')))
                }
                return Response(content=final_m3u8_output, headers=response_m3u8_headers, status_code=200)
            else:
                # Lógica de streaming para conteúdo não-M3U8 (existente)
                response_headers = dict(rp_resp.headers)
                response_headers["Access-Control-Allow-Origin"] = "*"
                response_headers.pop("transfer-encoding", None)
                response_headers.pop("content-length", None)
                # response_headers.pop("content-encoding", None) # Descomentar se houver problemas com encoding

                return Response(
                    content=rp_resp.aiter_bytes(), # Stream do conteúdo
                    status_code=rp_resp.status_code,
                    headers=response_headers,
                    media_type=rp_resp.headers.get("content-type", "application/octet-stream")
                )

    except httpx.HTTPStatusError as e: # Captura erros de rp_resp.raise_for_status()
        # e.response contém a resposta que causou o erro
        error_detail = f"Erro HTTP {e.response.status_code} ao buscar '{e.request.url}': {e.response.text[:200] if e.response.text else 'Sem corpo de resposta'}"
        print(error_detail)
        # Repassa o status code do erro, se possível, ou usa 502
        remote_status_code = e.response.status_code
        # Evitar repassar certos status codes diretamente ou mapeá-los
        if remote_status_code in [401, 403]: # Exemplo: não repassar erros de autenticação como se fossem do proxy
            status_to_return = 502 # Bad Gateway, pois o proxy não conseguiu obter o recurso
        elif 400 <= remote_status_code < 500:
             status_to_return = remote_status_code # Repassa erros do cliente (ex: 404 do destino)
        else: # Erros 5xx do destino
            status_to_return = 502 # Bad Gateway
        raise HTTPException(status_code=status_to_return, detail=error_detail)
    except httpx.RequestError as e: # Outros erros do httpx (ex: falha na conexão, timeout)
        error_detail = f"Erro de proxy HTTPX para '{original_url if 'original_url' in locals() else encoded_url}': {type(e).__name__} - {str(e)}"
        print(error_detail)
        raise HTTPException(status_code=502, detail=error_detail) # 502 Bad Gateway
    except Exception as e:
        error_detail = f"Erro inesperado no proxy para '{original_url if 'original_url' in locals() else encoded_url}': {type(e).__name__} - {str(e)}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=error_detail)


if __name__ == "__main__":
    import uvicorn
    # O servidor proxy_server.py (HTTP) deve rodar na porta 9000
    # Esta aplicação FastAPI pode rodar em outra porta, ex: 8000
    # Mas para o contexto do problema, onde /proxy/ é chamado em localhost:9000
    # assumimos que esta app FastAPI é quem responde na 9000.
    print("Aplicação FastAPI (incluindo /proxy/ e /{m3u_file}) rodando na porta 9000")
    uvicorn.run(app, host="0.0.0.0", port=9000)
