import os
import asyncio
import socket
import aiohttp
import zipfile
import plistlib
from aiohttp import web
from config import SIGNED_DIR, TEMP_DIR, SERVER_HOST, SERVER_PORT, PUBLIC_URL, ZSIGN_PATH
from bot.services.database import db
from bot.services.signer import IPASigner

_public_ip_cache = None
_bot_instance = None
signer = IPASigner(zsign_bin=ZSIGN_PATH)


def set_bot_instance(bot):
    global _bot_instance
    _bot_instance = bot


async def get_public_or_local_ip() -> str:
    global _public_ip_cache
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip("/")

    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if render_host:
        return f"https://{render_host.strip()}"

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
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(SIGNED_DIR, safe_filename)

    if not os.path.exists(file_path):
        return web.Response(status=404, text="File not found or expired.")

    response = web.FileResponse(file_path)
    response.headers["Content-Type"] = "application/octet-stream"
    response.headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    return response


def get_ipa_info(ipa_path: str) -> dict:
    info = {"bundle_id": "com.app.signed", "app_name": "SignedApp", "version": "1.0"}
    try:
        with zipfile.ZipFile(ipa_path, 'r') as zf:
            for name in zf.namelist():
                if name.startswith("Payload/") and name.endswith(".app/Info.plist"):
                    with zf.open(name) as fp:
                        plist_data = plistlib.load(fp)
                        info["bundle_id"] = plist_data.get("CFBundleIdentifier", info["bundle_id"])
                        info["app_name"] = (
                            plist_data.get("CFBundleDisplayName")
                            or plist_data.get("CFBundleName")
                            or info["app_name"]
                        )
                        info["version"] = str(
                            plist_data.get("CFBundleShortVersionString")
                            or plist_data.get("CFBundleVersion")
                            or "1.0"
                        )
                        break
    except Exception as e:
        print(f"[get_ipa_info] Info.plist read: {e}")
    return info


async def handle_plist(request: web.Request):
    filename = request.match_info.get("filename", "")
    safe_filename = os.path.basename(filename)
    if safe_filename.endswith(".plist"):
        safe_filename = safe_filename[:-6]
    if not safe_filename.endswith(".ipa"):
        ipa_filename = f"{safe_filename}.ipa"
    else:
        ipa_filename = safe_filename

    file_path = os.path.join(SIGNED_DIR, ipa_filename)
    if not os.path.exists(file_path):
        return web.Response(status=404, text="IPA not found")

    host_header = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or ""
    if host_header and "127.0.0.1" not in host_header and "localhost" not in host_header:
        proto = request.headers.get("X-Forwarded-Proto") or "https"
        https_base_url = f"{proto}://{host_header}"
    else:
        base_url = await get_public_or_local_ip()
        if base_url.startswith("http://") and "127.0.0.1" not in base_url and "localhost" not in base_url:
            https_base_url = "https://" + base_url[len("http://"):]
        else:
            https_base_url = base_url

    ipa_url = f"{https_base_url}/download/{ipa_filename}"
    meta = get_ipa_info(file_path)

    plist_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>items</key>
    <array>
        <dict>
            <key>assets</key>
            <array>
                <dict>
                    <key>kind</key>
                    <string>software-package</string>
                    <key>url</key>
                    <string>{ipa_url}</string>
                </dict>
            </array>
            <key>metadata</key>
            <dict>
                <key>bundle-identifier</key>
                <string>{meta['bundle_id']}</string>
                <key>bundle-version</key>
                <string>{meta['version']}</string>
                <key>kind</key>
                <string>software</string>
                <key>title</key>
                <string>{meta['app_name']}</string>
            </dict>
        </dict>
    </array>
</dict>
</plist>"""
    return web.Response(text=plist_xml, content_type="text/xml")


async def handle_install_page(request: web.Request):
    filename = request.match_info.get("filename", "")
    safe_filename = os.path.basename(filename)
    if safe_filename.endswith(".plist"):
        safe_filename = safe_filename[:-6]
    if not safe_filename.endswith(".ipa"):
        ipa_filename = f"{safe_filename}.ipa"
        base_name = safe_filename
    else:
        ipa_filename = safe_filename
        base_name = safe_filename[:-4]

    file_path = os.path.join(SIGNED_DIR, ipa_filename)
    host_header = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or ""
    if host_header and "127.0.0.1" not in host_header and "localhost" not in host_header:
        proto = request.headers.get("X-Forwarded-Proto") or "https"
        https_base_url = f"{proto}://{host_header}"
    else:
        base_url = await get_public_or_local_ip()
        if base_url.startswith("http://") and "127.0.0.1" not in base_url and "localhost" not in base_url:
            https_base_url = "https://" + base_url[len("http://"):]
        else:
            https_base_url = base_url

    meta = get_ipa_info(file_path) if os.path.exists(file_path) else {"app_name": "Signed App", "version": "1.0", "bundle_id": ""}
    manifest_url = f"{https_base_url}/plist/{base_name}.plist"
    itms_url = f"itms-services://?action=download-manifest&url={manifest_url}"
    download_url = f"{base_url}/download/{ipa_filename}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <title>Install {meta['app_name']}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f19; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }}
    .container {{ background: #161f30; border-radius: 24px; padding: 36px 24px; max-width: 400px; width: 100%; text-align: center; box-shadow: 0 20px 50px rgba(0,0,0,0.6); border: 1px solid #1e293b; }}
    .icon {{ width: 88px; height: 88px; border-radius: 20px; background: linear-gradient(135deg, #0284c7, #6366f1); margin: 0 auto 20px; display: flex; align-items: center; justify-content: center; font-size: 40px; box-shadow: 0 8px 24px rgba(2,132,199,0.4); }}
    h1 {{ margin: 0 0 6px 0; font-size: 22px; font-weight: 700; color: #f8fafc; }}
    p.meta {{ color: #94a3b8; font-size: 13px; margin: 0 0 28px 0; }}
    .btn {{ display: block; width: 100%; padding: 16px; border-radius: 14px; font-size: 17px; font-weight: 600; text-decoration: none; margin-bottom: 12px; transition: 0.2s; }}
    .btn-install {{ background: #0284c7; color: #fff; box-shadow: 0 4px 14px rgba(2,132,199,0.4); }}
    .btn-install:active {{ background: #0369a1; transform: scale(0.98); }}
    .btn-download {{ background: #1e293b; color: #38bdf8; }}
    .note {{ color: #64748b; font-size: 13px; margin-top: 20px; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="icon">📱</div>
    <h1>{meta['app_name']}</h1>
    <p class="meta">v{meta['version']} • Direct iOS Wireless Install</p>
    
    <a href="{itms_url}" class="btn btn-install" id="installBtn">📲 Tap to Install (डायरेक्ट इंस्टॉल)</a>
    <a href="{download_url}" class="btn btn-download">📁 Download .IPA File</a>

    <p class="note">👉 जब <b>"Install"</b> का पॉपअप आए, तो <b>Install</b> पर टैप करें। ऐप आपके iPhone होम स्क्रीन पर इंस्टॉल हो जाएगी।</p>
  </div>
  <script>
    if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {{
      setTimeout(function() {{
        window.location.href = "{itms_url}";
      }}, 500);
    }}
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


# Modern Web Upload Portal for >2GB IPAs
UPLOAD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Upload Large IPA (&gt;2GB)</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
    .card { background: #1e293b; border-radius: 16px; padding: 32px 24px; max-width: 480px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center; }
    h2 { margin: 0 0 10px 0; color: #38bdf8; font-size: 24px; }
    p { color: #94a3b8; font-size: 14px; margin: 0 0 20px 0; line-height: 1.5; }
    .dropzone { border: 2px dashed #475569; border-radius: 12px; padding: 40px 20px; cursor: pointer; transition: 0.2s; background: #0f172a; margin-bottom: 20px; }
    .dropzone:hover { border-color: #38bdf8; background: #1e293b; }
    .dropzone p { margin: 8px 0 0 0; color: #cbd5e1; }
    input[type=file] { display: none; }
    .btn { background: #0284c7; color: white; border: none; padding: 14px 20px; border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer; width: 100%; transition: 0.2s; }
    .btn:hover { background: #0369a1; }
    .btn:disabled { background: #475569; cursor: not-allowed; }
    .progress-container { width: 100%; background: #334155; border-radius: 8px; overflow: hidden; height: 12px; margin-top: 20px; display: none; }
    .progress-bar { height: 100%; width: 0%; background: #38bdf8; transition: width 0.1s ease; }
    #status { margin-top: 16px; font-size: 14px; font-weight: 500; }
    .success { color: #4ade80; }
    .error { color: #f87171; }
  </style>
</head>
<body>
  <div class="card">
    <h2>📲 Large IPA Uploader</h2>
    <p>Upload files of any size (&gt;2GB, 3GB, 5GB+). Once uploaded, your IPA will be signed and delivered automatically to your Telegram!</p>
    
    <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
      <div style="font-size: 40px;">📁</div>
      <p id="filenameDisplay">Tap or Drag IPA file here</p>
      <input type="file" id="fileInput" accept=".ipa,.zip" onchange="handleFileSelected(this.files)">
    </div>

    <button class="btn" id="uploadBtn" onclick="startUpload()" disabled>Upload & Sign IPA</button>

    <div class="progress-container" id="progressContainer">
      <div class="progress-bar" id="progressBar"></div>
    </div>
    <div id="status"></div>
  </div>

  <script>
    let selectedFile = null;
    const urlParams = new URLSearchParams(window.location.search);
    const userId = urlParams.get('user_id');

    function handleFileSelected(files) {
      if (files && files.length > 0) {
        selectedFile = files[0];
        const sizeMB = (selectedFile.size / (1024 * 1024)).toFixed(1);
        const sizeGB = (selectedFile.size / (1024 * 1024 * 1024)).toFixed(2);
        const displaySize = selectedFile.size >= 1024*1024*1024 ? sizeGB + ' GB' : sizeMB + ' MB';
        document.getElementById('filenameDisplay').innerHTML = '<b>' + selectedFile.name + '</b><br><small>Size: ' + displaySize + '</small>';
        document.getElementById('uploadBtn').disabled = false;
      }
    }

    function startUpload() {
      if (!selectedFile) return;
      if (!userId) {
        document.getElementById('status').className = 'error';
        document.getElementById('status').innerText = 'Error: Missing user_id parameter in URL!';
        return;
      }

      document.getElementById('uploadBtn').disabled = true;
      document.getElementById('progressContainer').style.display = 'block';
      const status = document.getElementById('status');
      status.className = '';
      status.innerText = 'Uploading... Please keep this page open.';

      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload_ipa?user_id=' + encodeURIComponent(userId) + '&filename=' + encodeURIComponent(selectedFile.name), true);

      xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          document.getElementById('progressBar').style.width = percent + '%';
          const loadedMB = (e.loaded / (1024*1024)).toFixed(1);
          const totalMB = (e.total / (1024*1024)).toFixed(1);
          status.innerText = 'Uploading: ' + percent + '% (' + loadedMB + ' MB / ' + totalMB + ' MB)';
        }
      };

      xhr.onload = function() {
        if (xhr.status === 200) {
          status.className = 'success';
          status.innerHTML = '🎉 <b>Upload Complete!</b><br>Your IPA is now being signed. Check your Telegram chat for the signed download link!';
        } else {
          status.className = 'error';
          status.innerText = 'Upload failed with code: ' + xhr.status + ' (' + xhr.responseText + ')';
          document.getElementById('uploadBtn').disabled = false;
        }
      };

      xhr.onerror = function() {
        status.className = 'error';
        status.innerText = 'Upload failed. Connection lost.';
        document.getElementById('uploadBtn').disabled = false;
      };

      xhr.send(selectedFile);
    }
  </script>
</body>
</html>
"""

async def handle_upload_page(request: web.Request):
    return web.Response(text=UPLOAD_HTML, content_type="text/html")


async def handle_api_upload_ipa(request: web.Request):
    user_id_str = request.query.get("user_id", "")
    if not user_id_str.isdigit():
        return web.Response(status=400, text="Missing or invalid user_id")

    user_id = int(user_id_str)
    filename = request.query.get("filename", "app.ipa")
    clean_name = os.path.basename(filename)
    if not clean_name.lower().endswith((".ipa", ".zip")):
        clean_name += ".ipa"

    target_path = os.path.join(TEMP_DIR, f"input_{user_id}.ipa")

    # Stream file to disk in 4MB high-speed chunks
    try:
        with open(target_path, "wb", buffering=4 * 1024 * 1024) as f:
            while True:
                chunk = await request.content.read(4 * 1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        return web.Response(status=500, text=f"File stream error: {e}")

    # Launch signing task in background
    asyncio.create_task(run_background_signing(user_id, target_path, clean_name))

    return web.Response(text="File uploaded successfully! Signing started.")


async def run_background_signing(user_id: int, input_ipa_path: str, original_filename: str):
    user_data = db.get_user(user_id) or {}
    cert_info = db.get_user_cert_info(user_id)

    p12_path = cert_info.get("p12_path", "")
    p12_pass = cert_info.get("p12_password", "")
    prov_path = cert_info.get("mobileprovision_path", "")
    bundle_id = user_data.get("custom_bundle_id") or None
    app_name = user_data.get("custom_app_name") or None
    custom_icon = user_data.get("custom_icon_path") or None
    dylib_path = user_data.get("inject_dylib_path") or None

    clean_basename = "".join(c for c in original_filename if c.isalnum() or c in "._-")
    output_filename = f"signed_{user_id}_{clean_basename}"
    output_ipa_path = os.path.join(SIGNED_DIR, output_filename)

    if _bot_instance:
        try:
            await _bot_instance.send_message(
                chat_id=user_id,
                text=f"⚙️ **Large IPA Uploaded via Web Portal!**\n\nFile: `{original_filename}`\nSigning in progress... Please wait...",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    loop = asyncio.get_running_loop()
    success, sign_log = await loop.run_in_executor(
        None,
        signer.sign,
        input_ipa_path,
        p12_path,
        p12_pass,
        prov_path,
        output_ipa_path,
        bundle_id,
        app_name,
        custom_icon,
        dylib_path
    )

    try:
        if os.path.exists(input_ipa_path):
            os.remove(input_ipa_path)
    except Exception:
        pass

    if not _bot_instance:
        return

    if not success:
        try:
            await _bot_instance.send_message(
                chat_id=user_id,
                text=f"❌ **Signing Failed!**\n\n```\n{sign_log}\n```\nPlease verify your certificate password or provisioning profile.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    db.increment_sign_count(user_id)
    file_bytes = os.path.getsize(output_ipa_path)
    file_size_gb = file_bytes / (1024 * 1024 * 1024)
    file_size_mb = file_bytes / (1024 * 1024)
    size_display = f"{file_size_gb:.2f} GB" if file_size_gb >= 1.0 else f"{file_size_mb:.2f} MB"

    base_url = await get_public_or_local_ip()
    install_url = f"{base_url}/install/{output_filename}"
    download_link = f"{base_url}/download/{output_filename}"

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    install_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📲 Direct Install on iPhone (डायरेक्ट इंस्टॉल)", url=install_url)
        ],
        [
            InlineKeyboardButton("📁 Download .IPA File", url=download_link)
        ]
    ])

    msg = (
        f"✅ **IPA Signed!**\n\n"
        f"📱 **File:** `{original_filename}`\n"
        f"📦 **Size:** `{size_display}`\n"
        f"🔑 **Cert:** `{cert_info.get('cert_name') or 'Custom Saved'}` (Saved ✅)\n\n"
        f"👇 **iPhone में तुरंत इंस्टॉल करने के लिए नीचे बटन दबाएं:**"
    )

    try:
        if file_size_mb <= 2000:
            from bot.services.telegram_mtproto import upload_direct_media
            await upload_direct_media(
                chat_id=user_id,
                file_path=output_ipa_path,
                file_name=original_filename,
                caption=msg
            )
        await _bot_instance.send_message(
            chat_id=user_id,
            text="📲 **Direct iPhone Installation Ready!**\n\n👉 नीचे 'Direct Install' दबाएं:",
            reply_markup=install_keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[run_background_signing] Notification error: {e}")
        try:
            await _bot_instance.send_message(
                chat_id=user_id,
                text=msg,
                reply_markup=install_keyboard,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception:
            pass


def create_web_app() -> web.Application:
    # Set client_max_size to 10GB for arbitrary large file uploads
    app = web.Application(client_max_size=10 * 1024 * 1024 * 1024)
    app.router.add_get("/", handle_root)
    app.router.add_get("/healthz", handle_health)
    app.router.add_get("/upload", handle_upload_page)
    app.router.add_post("/api/upload_ipa", handle_api_upload_ipa)
    app.router.add_get("/download/{filename}", handle_download)
    app.router.add_get("/plist/{filename}", handle_plist)
    app.router.add_get("/install/{filename}", handle_install_page)
    return app


async def start_web_server(bot=None):
    if bot:
        set_bot_instance(bot)
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, SERVER_HOST, SERVER_PORT)
    try:
        await site.start()
        print(f"🌐 Large File Download & Upload Web Server running on {SERVER_HOST}:{SERVER_PORT}")
    except Exception as e:
        print(f"⚠️ Could not start web server on port {SERVER_PORT}: {e}")
