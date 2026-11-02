import os
import asyncio
import socket
import aiohttp
from aiohttp import web
from config import SIGNED_DIR, SERVER_HOST, SERVER_PORT, PUBLIC_URL

_public_ip_cache = None

async def get_public_or_local_ip() -> str:
    global _public_ip_cache
    if PUBLIC_URL:
        return PUBLIC_URL.rstrip("/")
    if _public_ip_cache:
        return _public_ip_cache

    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.ipify.org?format=text") as resp:
                if resp.status == 200:
                    ip = (await resp.text()).strip()
                    _public_ip_cache = f"http://{ip}:{SERVER_PORT}"
                    return _public_ip_cache
    except Exception:
        pass

    # Fallback to local machine network IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        _public_ip_cache = f"http://{local_ip}:{SERVER_PORT}"
        return _public_ip_cache
    except Exception:
        _public_ip_cache = f"http://127.0.0.1:{SERVER_PORT}"
        return _public_ip_cache


async def handle_root(request: web.Request):
    return web.Response(text="iOS IPA Signer Telegram Bot is active & running 24/7!", content_type="text/plain")


async def handle_health(request: web.Request):
    return web.json_response({"status": "healthy", "service": "ipa-signer-bot"})


async def handle_download(request: web.Request):
    filename = request.match_info.get("filename", "")
    # Prevent directory traversal
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(SIGNED_DIR, safe_filename)

    if not os.path.exists(file_path):
        return web.Response(status=404, text="File not found or expired.")

    # FileResponse handles chunking, HTTP Range (resuming), and arbitrary large files (> 2GB)
    response = web.FileResponse(file_path)
    response.headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    return response


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/healthz", handle_health)
    app.router.add_get("/download/{filename}", handle_download)
    return app


async def start_web_server():
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, SERVER_HOST, SERVER_PORT)
    try:
        await site.start()
        print(f"🌐 Large File Download Web Server running on {SERVER_HOST}:{SERVER_PORT}")
    except Exception as e:
        print(f"⚠️ Could not start web server on port {SERVER_PORT}: {e}")
