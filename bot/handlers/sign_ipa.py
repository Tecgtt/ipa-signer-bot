import os
import time
import aiohttp
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from config import TEMP_DIR, SIGNED_DIR, ZSIGN_PATH, MAX_FILE_SIZE_MB
from bot.keyboards import get_cancel_keyboard, get_main_keyboard, get_cert_menu_keyboard
from bot.services.database import db
from bot.services.signer import IPASigner
from bot.services.web_server import get_public_or_local_ip
from bot.services.telegram_mtproto import download_direct_media, upload_direct_media
from bot.handlers.admin import is_admin

signer = IPASigner(zsign_bin=ZSIGN_PATH)


async def sign_ipa_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    cert_info = db.get_user_cert_info(user_id)
    if not cert_info["is_ready"]:
        await update.message.reply_text(
            "⚠️ **Certificate Required!**\n"
            "Please upload your `.p12` & `.mobileprovision` first.",
            reply_markup=get_cert_menu_keyboard(has_cert=False),
            parse_mode="Markdown"
        )
        return

    context.user_data["waiting_for"] = "sign_ipa_input"
    cert_display = cert_info.get("cert_name") or "Saved Certificate"

    msg = (
        "📲 **Sign IPA**\n\n"
        f"🔑 **Cert:** `{cert_display}` (Saved ✅)\n\n"
        "👉 **Send your `.ipa` file or download link now:**"
    )

    await update.message.reply_text(
        msg,
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )


def convert_to_direct_url(url: str) -> str:
    import re
    if "drive.google.com" in url:
        m = re.search(r'(?:file/d/|id=)([a-zA-Z0-9_-]+)', url)
        if m:
            return f"https://drive.google.com/uc?export=download&id={m.group(1)}&confirm=t"
    if "dropbox.com" in url:
        if "dl=0" in url:
            return url.replace("dl=0", "dl=1")
        elif not url.endswith("dl=1"):
            return url + ("&dl=1" if "?" in url else "?dl=1")
    return url


async def download_file_from_url(url: str, dest_path: str, status_msg=None) -> bool:
    try:
        url = convert_to_direct_url(url)
        timeout = aiohttp.ClientTimeout(total=7200)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    return False
                
                total_size = response.content_length or 0
                downloaded = 0
                last_update = 0

                with open(dest_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(4 * 1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if status_msg and total_size > 0 and (downloaded - last_update > 40 * 1024 * 1024):
                            last_update = downloaded
                            mb_done = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            pct = int(mb_done / mb_total * 100)
                            try:
                                await status_msg.edit_text(
                                    f"⚡ **Downloading from Link ({pct}%)...**\n`{mb_done:.1f} MB / {mb_total:.1f} MB`",
                                    parse_mode="Markdown"
                                )
                            except Exception:
                                pass

                return True
    except Exception as e:
        print(f"[download_file_from_url] Error: {e}")
        return False


async def process_ipa_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_data = db.get_user(user_id) or {}
    cert_info = db.get_user_cert_info(user_id)
    context.user_data.pop("waiting_for", None)

    input_ipa_path = os.path.join(TEMP_DIR, f"input_{user_id}.ipa")
    original_filename = "app.ipa"

    main_keyboard = get_main_keyboard(is_admin=is_admin(user))

    last_edit = [0.0]

    async def update_download_progress(current: int, total: int):
        now = time.time()
        if total > 0 and (now - last_edit[0] >= 2.0 or current == total):
            last_edit[0] = now
            pct = int((current / total) * 100)
            mb_cur = current / (1024 * 1024)
            mb_tot = total / (1024 * 1024)
            try:
                await status_msg.edit_text(
                    f"⚡ **Downloading IPA ({pct}%)...** `{mb_cur:.1f}/{mb_tot:.1f}MB`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    async def update_upload_progress(current: int, total: int):
        now = time.time()
        if total > 0 and (now - last_edit[0] >= 2.0 or current == total):
            last_edit[0] = now
            pct = int((current / total) * 100)
            mb_cur = current / (1024 * 1024)
            mb_tot = total / (1024 * 1024)
            try:
                await status_msg.edit_text(
                    f"⚡ **Uploading Signed IPA ({pct}%)...** `{mb_cur:.1f}/{mb_tot:.1f}MB`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    # 1. URL link sent
    if update.message.text:
        text = update.message.text.strip()
        if text.startswith("http://") or text.startswith("https://"):
            status_msg = await update.message.reply_text("⚡ **Downloading from link...**", parse_mode="Markdown")
            success = await download_file_from_url(text, input_ipa_path, status_msg=status_msg)
            if not success:
                await status_msg.edit_text("❌ Download failed. Ensure link is direct and valid.")
                return
            original_filename = text.split("/")[-1].split("?")[0] or "app.ipa"
            if not original_filename.endswith(".ipa"):
                original_filename += ".ipa"
        else:
            await update.message.reply_text("❌ Please send a valid `.ipa` file or link.", reply_markup=main_keyboard)
            return

    # 2. Document file sent
    elif update.message.document:
        doc = update.message.document
        original_filename = doc.file_name or "app.ipa"
        if not original_filename.lower().endswith((".ipa", ".zip")):
            await update.message.reply_text("❌ Not an `.ipa` file.", reply_markup=main_keyboard)
            return

        file_size_bytes = doc.file_size or 0
        file_size_mb = file_size_bytes / (1024 * 1024)

        status_msg = await update.message.reply_text(
            f"⚡ **Downloading `{original_filename}` ({file_size_mb:.1f} MB)...**",
            parse_mode="Markdown"
        )

        download_success = False

        try:
            download_success = await download_direct_media(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                dest_path=input_ipa_path,
                progress_fn=update_download_progress
            )
        except Exception:
            download_success = False

        if not download_success:
            try:
                file_obj = await doc.get_file()
                await file_obj.download_to_drive(input_ipa_path)
                download_success = True
            except Exception:
                download_success = False

        if not download_success or not os.path.exists(input_ipa_path) or os.path.getsize(input_ipa_path) == 0:
            await status_msg.edit_text("❌ Direct download error. Please try sending via Google Drive link.")
            return
    else:
        await update.message.reply_text("❌ Send an IPA file or link.", reply_markup=main_keyboard)
        return

    # Instant signing
    await status_msg.edit_text("⚡ **Signing IPA...**", parse_mode="Markdown")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)

    clean_basename = "".join(c for c in original_filename if c.isalnum() or c in "._-")
    output_filename = f"signed_{user_id}_{clean_basename}"
    output_ipa_path = os.path.join(SIGNED_DIR, output_filename)

    p12_path = cert_info.get("p12_path", "")
    p12_pass = cert_info.get("p12_password", "")
    prov_path = cert_info.get("mobileprovision_path", "")
    bundle_id = user_data.get("custom_bundle_id") or None
    app_name = user_data.get("custom_app_name") or None
    custom_icon = user_data.get("custom_icon_path") or None
    dylib_path = user_data.get("inject_dylib_path") or None

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

    if not success:
        await status_msg.edit_text(
            f"❌ **Signing Failed!**\n\n```\n{sign_log[:300]}\n```\nPlease verify password or mobileprovision.",
            parse_mode="Markdown"
        )
        return

    db.increment_sign_count(user_id)
    file_bytes = os.path.getsize(output_ipa_path)
    file_size_mb = file_bytes / (1024 * 1024)
    file_size_gb = file_bytes / (1024 * 1024 * 1024)
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

    caption = (
        f"✅ **IPA Signed!**\n\n"
        f"📱 **File:** `{original_filename}`\n"
        f"📦 **Size:** `{size_display}`\n"
        f"🔑 **Cert:** `{cert_info.get('cert_name') or 'Custom'}`\n\n"
        f"👇 **iPhone में तुरंत इंस्टॉल करने के लिए नीचे बटन दबाएं:**"
    )

    uploaded_in_chat = False
    if file_size_mb <= 2000:
        last_edit[0] = 0.0
        await status_msg.edit_text(f"⚡ **Uploading to Telegram...**", parse_mode="Markdown")
        try:
            uploaded_in_chat = await upload_direct_media(
                chat_id=update.effective_chat.id,
                file_path=output_ipa_path,
                file_name=original_filename,
                caption=caption,
                progress_fn=update_upload_progress
            )
        except Exception:
            uploaded_in_chat = False

    if not uploaded_in_chat and file_size_mb <= MAX_FILE_SIZE_MB:
        try:
            with open(output_ipa_path, "rb") as signed_file:
                await update.message.reply_document(
                    document=signed_file,
                    filename=original_filename,
                    caption=caption,
                    reply_markup=install_keyboard,
                    parse_mode="Markdown"
                )
            uploaded_in_chat = True
        except Exception:
            pass

    # Send 1-click install button in chat
    await update.message.reply_text(
        "📲 **Direct iPhone Installation Ready!**\n\n"
        "👉 नीचे **'Direct Install on iPhone'** बटन दबाएं। Safari में 'Install' का पॉपअप आएगा और ऐप सीधे आपके iPhone पर इंस्टॉल हो जाएगी:",
        reply_markup=install_keyboard,
        parse_mode="Markdown"
    )

    try:
        await status_msg.delete()
    except Exception:
        pass
    return
