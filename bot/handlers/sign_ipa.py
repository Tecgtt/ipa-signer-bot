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
    user_data = db.get_user(user_id) or {}

    # Check certificate readiness using permanent storage check
    cert_info = db.get_user_cert_info(user_id)

    if not cert_info["is_ready"]:
        missing = []
        if not cert_info["has_p12"]:
            missing.append("`.p12` Certificate")
        if not cert_info["has_prov"]:
            missing.append("`.mobileprovision` Profile")

        await update.message.reply_text(
            f"⚠️ **Certificate Missing!**\n\n"
            f"You need to provide your certificate before signing IPAs.\n"
            f"Missing items: {', '.join(missing)}\n\n"
            "👉 *Please tap `📦 My Certificate` to upload them now.*",
            reply_markup=get_cert_menu_keyboard(has_cert=(cert_info["has_p12"] or cert_info["has_prov"])),
            parse_mode="Markdown"
        )
        return

    context.user_data["waiting_for"] = "sign_ipa_input"

    base_url = await get_public_or_local_ip()
    upload_portal_url = f"{base_url}/upload?user_id={user_id}"
    cert_display = cert_info.get("cert_name") or "Saved Certificate"

    msg = (
        "📲 **Ready to Sign IPA!**\n\n"
        f"🔑 **Active Certificate:** `{cert_display}` (🟢 Permanently Saved)\n"
        "*(Note: You do NOT need to upload your certificate again!)*\n\n"
        "Send your IPA file in any of the following ways:\n\n"
        "1. 📎 **Direct in Chat (Up to 2 GB):**\n"
        "   Simply send the `.ipa` file directly here in Telegram chat (High-speed MTProto 🚀).\n\n"
        "2. 🔗 **Direct Download Link:**\n"
        "   Send any direct link, Google Drive, Dropbox, or MediaFire link.\n\n"
        "3. 🌐 **Web Upload Portal (For massive files up to 10 GB):**\n"
        f"   👉 [Click Here to Open Web Upload Portal]({upload_portal_url})\n\n"
        "⚙️ *Current active settings:*\n"
        f"• **Bundle ID:** `{user_data.get('custom_bundle_id') or 'Default'}`\n"
        f"• **App Name:** `{user_data.get('custom_app_name') or 'Default'}`\n"
        f"• **Custom Thumbnail:** `{'Active ✅' if user_data.get('custom_icon_path') else 'None ⚪'}`\n\n"
        "👇 *Send your IPA file or link now:*"
    )

    await update.message.reply_text(
        msg,
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


def convert_to_direct_url(url: str) -> str:
    import re
    # Google Drive conversion
    if "drive.google.com" in url:
        m = re.search(r'(?:file/d/|id=)([a-zA-Z0-9_-]+)', url)
        if m:
            return f"https://drive.google.com/uc?export=download&id={m.group(1)}&confirm=t"
    # Dropbox conversion
    if "dropbox.com" in url:
        if "dl=0" in url:
            return url.replace("dl=0", "dl=1")
        elif not url.endswith("dl=1"):
            return url + ("&dl=1" if "?" in url else "?dl=1")
    return url


async def download_file_from_url(url: str, dest_path: str, status_msg=None) -> bool:
    try:
        url = convert_to_direct_url(url)
        # 2-hour timeout for massive files (>2GB)
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
                        chunk = await response.content.read(4 * 1024 * 1024)  # 4MB chunks for fast link stream
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update download progress every 50MB
                        if status_msg and total_size > 0 and (downloaded - last_update > 50 * 1024 * 1024):
                            last_update = downloaded
                            mb_done = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            try:
                                await status_msg.edit_text(
                                    f"⏳ **Downloading IPA from Link...**\n`{mb_done:.1f} MB / {mb_total:.1f} MB ({int(mb_done/mb_total*100)}%)`",
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

    # Helper for throttled progress bar updates
    last_edit = [0.0]

    async def update_download_progress(current: int, total: int):
        now = time.time()
        if total > 0 and (now - last_edit[0] >= 2.5 or current == total):
            last_edit[0] = now
            pct = int((current / total) * 100)
            mb_cur = current / (1024 * 1024)
            mb_tot = total / (1024 * 1024)
            filled = min(10, max(0, pct // 10))
            bar = "█" * filled + "░" * (10 - filled)
            try:
                await status_msg.edit_text(
                    f"⚡ **Downloading IPA at High Speed ({pct}%)...**\n"
                    f"`[{bar}]` {mb_cur:.1f} MB / {mb_tot:.1f} MB",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    async def update_upload_progress(current: int, total: int):
        now = time.time()
        if total > 0 and (now - last_edit[0] >= 2.5 or current == total):
            last_edit[0] = now
            pct = int((current / total) * 100)
            mb_cur = current / (1024 * 1024)
            mb_tot = total / (1024 * 1024)
            filled = min(10, max(0, pct // 10))
            bar = "█" * filled + "░" * (10 - filled)
            try:
                await status_msg.edit_text(
                    f"⚡ **Uploading Signed IPA at High Speed ({pct}%)...**\n"
                    f"`[{bar}]` {mb_cur:.1f} MB / {mb_tot:.1f} MB",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    # 1. User sent a URL link
    if update.message.text:
        text = update.message.text.strip()
        if text.startswith("http://") or text.startswith("https://"):
            status_msg = await update.message.reply_text("⏳ **Downloading IPA from provided link...**", parse_mode="Markdown")
            success = await download_file_from_url(text, input_ipa_path, status_msg=status_msg)
            if not success:
                await status_msg.edit_text("❌ Failed to download IPA from the provided link. Please ensure it's a direct, accessible URL.")
                return
            original_filename = text.split("/")[-1].split("?")[0] or "app.ipa"
            if not original_filename.endswith(".ipa"):
                original_filename += ".ipa"
        else:
            await update.message.reply_text(
                "❌ Please send either an `.ipa` file or a valid `http`/`https` link.",
                reply_markup=main_keyboard
            )
            return

    # 2. User sent an IPA file directly in chat
    elif update.message.document:
        doc = update.message.document
        original_filename = doc.file_name or "app.ipa"
        if not original_filename.lower().endswith((".ipa", ".zip")):
            await update.message.reply_text(
                "❌ The uploaded file is not an IPA (`.ipa`) file.",
                reply_markup=main_keyboard
            )
            return

        file_size_bytes = doc.file_size or 0
        file_size_mb = file_size_bytes / (1024 * 1024)

        status_msg = await update.message.reply_text(
            f"⚡ **Downloading `{original_filename}` ({file_size_mb:.1f} MB)...**\n`Connecting high-speed MTProto pipeline...`",
            parse_mode="Markdown"
        )

        download_success = False

        # Attempt 1: High-Speed Telethon MTProto (supports up to 2000 MB / 2 GB direct in chat)
        try:
            download_success = await download_direct_media(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                dest_path=input_ipa_path,
                progress_fn=update_download_progress
            )
        except Exception as e:
            print(f"[Telethon MTProto download exception]: {e}")
            download_success = False

        # Attempt 2: Standard Bot API get_file fallback
        if not download_success:
            try:
                file_obj = await doc.get_file()
                await file_obj.download_to_drive(input_ipa_path)
                download_success = True
            except Exception:
                download_success = False

        if not download_success or not os.path.exists(input_ipa_path) or os.path.getsize(input_ipa_path) == 0:
            base_url = await get_public_or_local_ip()
            upload_portal_url = f"{base_url}/upload?user_id={user_id}"
            await status_msg.edit_text(
                "⚠️ **Could not download file directly from Telegram!**\n\n"
                "Telegram sets an in-chat cap of 2 GB.\n\n"
                "🚀 **Use our Web Upload Portal for unlimited file sizes (up to 10 GB):**\n"
                f"👉 [Click Here to Upload Large IPA]({upload_portal_url})\n\n"
                "*(Or upload your IPA to Google Drive / MediaFire and send the link here)*",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            return
    else:
        await update.message.reply_text(
            "❌ Invalid input. Please send an IPA file or a direct download link.",
            reply_markup=main_keyboard
        )
        return

    # Start signing process
    await status_msg.edit_text("⚙️ **Signing IPA in progress... Please wait...**\n`Injecting signature & certificates...`", parse_mode="Markdown")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)

    clean_basename = "".join(c for c in original_filename if c.isalnum() or c in "._-")
    output_filename = f"signed_{user_id}_{clean_basename}"
    output_ipa_path = os.path.join(SIGNED_DIR, output_filename)

    # Load signing options from permanently saved certificate
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

    # Clean input file
    try:
        if os.path.exists(input_ipa_path):
            os.remove(input_ipa_path)
    except Exception:
        pass

    if not success:
        await status_msg.edit_text(
            f"❌ **Signing Failed!**\n\n"
            f"⚠️ **Error Details:**\n```\n{sign_log}\n```\n"
            "Please check your `.p12` password or verify your provisioning profile.",
            parse_mode="Markdown"
        )
        return

    db.increment_sign_count(user_id)
    file_bytes = os.path.getsize(output_ipa_path)
    file_size_mb = file_bytes / (1024 * 1024)
    file_size_gb = file_bytes / (1024 * 1024 * 1024)

    size_display = f"{file_size_gb:.2f} GB" if file_size_gb >= 1.0 else f"{file_size_mb:.2f} MB"

    base_url = await get_public_or_local_ip()
    download_link = f"{base_url}/download/{output_filename}"

    caption = (
        f"✅ **IPA Signed Successfully!**\n\n"
        f"📱 **File:** `{original_filename}`\n"
        f"📦 **Size:** `{size_display}`\n"
        f"🆔 **Bundle ID:** `{bundle_id or 'Original'}`\n"
        f"🏷️ **App Name:** `{app_name or 'Original'}`\n"
        f"🔑 **Certificate:** `{cert_info.get('cert_name') or 'Custom Saved'}` (Permanently Saved ✅)\n\n"
        f"🚀 **Direct Download Link:** [Click to Download]({download_link})\n\n"
        "📲 **How to Install:**\n"
        "• Send to **TrollStore** / **Scarlet** / **Esign**\n"
        "• Or sideload with **AltStore** / **Sideloadly**"
    )

    # If file <= 2000 MB: try direct Telegram in-chat upload via high-speed MTProto
    uploaded_in_chat = False
    if file_size_mb <= 2000:
        last_edit[0] = 0.0
        await status_msg.edit_text(f"⚡ **Uploading signed `{original_filename}` to Telegram chat at high speed...**", parse_mode="Markdown")
        try:
            uploaded_in_chat = await upload_direct_media(
                chat_id=update.effective_chat.id,
                file_path=output_ipa_path,
                file_name=original_filename,
                caption=caption,
                progress_fn=update_upload_progress
            )
        except Exception as e:
            print(f"[Direct MTProto upload error]: {e}")
            uploaded_in_chat = False

    # Fallback to standard Bot API if <= 50MB and MTProto didn't send
    if not uploaded_in_chat and file_size_mb <= MAX_FILE_SIZE_MB:
        try:
            with open(output_ipa_path, "rb") as signed_file:
                await update.message.reply_document(
                    document=signed_file,
                    filename=original_filename,
                    caption=caption,
                    reply_markup=main_keyboard,
                    parse_mode="Markdown"
                )
            uploaded_in_chat = True
        except Exception:
            pass

    if uploaded_in_chat:
        try:
            await status_msg.delete()
        except Exception:
            pass
        return

    # If file was > 2GB or direct in-chat upload was bypassed: deliver high-speed download link
    large_file_message = (
        caption + "\n\n"
        f"🚀 **Direct High-Speed Download Link:**\n"
        f"🔗 [Click Here to Download Signed IPA]({download_link})\n\n"
        f"`{download_link}`\n\n"
        "*(Link is active and supports direct download into Safari / TrollStore / Esign)*"
    )
    await status_msg.edit_text(
        large_file_message,
        reply_markup=main_keyboard,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
