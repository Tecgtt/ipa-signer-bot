import os
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
from bot.handlers.admin import is_admin

signer = IPASigner(zsign_bin=ZSIGN_PATH)


async def sign_ipa_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_data = db.get_user(user_id) or {}

    p12_path = user_data.get("p12_path")
    prov_path = user_data.get("mobileprovision_path")

    # Check certificate readiness
    has_p12 = p12_path and os.path.exists(p12_path)
    has_prov = prov_path and os.path.exists(prov_path)

    if not has_p12 or not has_prov:
        missing = []
        if not has_p12:
            missing.append("`.p12` Certificate")
        if not has_prov:
            missing.append("`.mobileprovision` Profile")

        await update.message.reply_text(
            f"⚠️ **Certificate Missing!**\n\n"
            f"You need to provide your certificate before signing IPAs.\n"
            f"Missing items: {', '.join(missing)}\n\n"
            "👉 *Please tap `📦 My Certificate` to upload them now.*",
            reply_markup=get_cert_menu_keyboard(has_cert=(has_p12 or has_prov)),
            parse_mode="Markdown"
        )
        return

    context.user_data["waiting_for"] = "sign_ipa_input"

    msg = (
        "📲 **Ready to Sign IPA!**\n\n"
        "Send the IPA file you wish to sign:\n"
        "1. 📎 **Upload IPA file directly** (under 50MB via Telegram)\n"
        "2. 🔗 **Or send a direct download link** (for files up to & over 2GB, e.g. `https://.../app.ipa`)\n\n"
        "⚙️ *Current active settings:*\n"
        f"• **Bundle ID:** `{user_data.get('custom_bundle_id') or 'Default'}`\n"
        f"• **App Name:** `{user_data.get('custom_app_name') or 'Default'}`\n"
        f"• **Custom Thumbnail:** `{'Active ✅' if user_data.get('custom_icon_path') else 'None ⚪'}`\n\n"
        "👇 *Send your IPA file or link now:*"
    )

    await update.message.reply_text(
        msg,
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )


async def download_file_from_url(url: str, dest_path: str, status_msg=None) -> bool:
    try:
        # 1-hour timeout for massive files (>2GB)
        timeout = aiohttp.ClientTimeout(total=3600)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return False
                
                total_size = response.content_length or 0
                downloaded = 0
                last_update = 0

                with open(dest_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(2 * 1024 * 1024)  # 2MB chunks
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
                                    f"⏳ **Downloading IPA...**\n`{mb_done:.1f} MB / {mb_total:.1f} MB ({int(mb_done/mb_total*100)}%)`",
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
    context.user_data.pop("waiting_for", None)

    input_ipa_path = os.path.join(TEMP_DIR, f"input_{user_id}.ipa")
    original_filename = "app.ipa"

    main_keyboard = get_main_keyboard(is_admin=is_admin(user))

    # Check if user sent a URL or a Telegram document
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
    elif update.message.document:
        doc = update.message.document
        original_filename = doc.file_name or "app.ipa"
        if not original_filename.lower().endswith((".ipa", ".zip")):
            await update.message.reply_text(
                "❌ The uploaded file is not an IPA (`.ipa`) file.",
                reply_markup=main_keyboard
            )
            return

        status_msg = await update.message.reply_text("⏳ **Downloading IPA from Telegram...**", parse_mode="Markdown")
        try:
            file_obj = await doc.get_file()
            await file_obj.download_to_drive(input_ipa_path)
        except Exception as e:
            await status_msg.edit_text(
                f"❌ Telegram download error: {e}\n\n"
                "💡 *Note:* Telegram restricts direct bot uploads to 20MB. For larger files (up to & over 2GB), please upload the IPA to Google Drive, Dropbox, or any direct file host and send the link here!"
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

    # Load signing options
    p12_path = user_data.get("p12_path", "")
    p12_pass = user_data.get("p12_password", "")
    prov_path = user_data.get("mobileprovision_path", "")
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

    caption = (
        f"✅ **IPA Signed Successfully!**\n\n"
        f"📱 **File:** `{original_filename}`\n"
        f"📦 **Size:** `{size_display}`\n"
        f"🆔 **Bundle ID:** `{bundle_id or 'Original'}`\n"
        f"🏷️ **App Name:** `{app_name or 'Original'}`\n"
        f"🔑 **Certificate:** `{user_data.get('cert_name') or 'Custom'}`\n\n"
        "📲 **How to Install:**\n"
        "• Send to **TrollStore** / **Scarlet** / **Esign**\n"
        "• Or sideload with **AltStore** / **Sideloadly**"
    )

    # If file size <= 50MB (standard Telegram bot direct upload)
    if file_size_mb <= MAX_FILE_SIZE_MB:
        try:
            with open(output_ipa_path, "rb") as signed_file:
                await update.message.reply_document(
                    document=signed_file,
                    filename=original_filename,
                    caption=caption,
                    reply_markup=main_keyboard,
                    parse_mode="Markdown"
                )
            await status_msg.delete()
            return
        except Exception:
            pass

    # For files > 50MB and especially > 2GB: Provide direct high-speed HTTP download link!
    base_url = await get_public_or_local_ip()
    download_link = f"{base_url}/download/{output_filename}"

    large_file_message = (
        caption + "\n\n"
        f"🚀 **Direct Download Link (Unlimited Size / >2GB):**\n"
        f"🔗 [Click Here to Download Signed IPA]({download_link})\n\n"
        f"`{download_link}`\n\n"
        "*(Link is valid and supports high-speed download directly into Safari / TrollStore)*"
    )

    await status_msg.edit_text(
        large_file_message,
        reply_markup=main_keyboard,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
