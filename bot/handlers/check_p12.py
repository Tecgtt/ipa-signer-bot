import os
from telegram import Update
from telegram.ext import ContextTypes
from config import TEMP_DIR
from bot.keyboards import get_cancel_keyboard, get_main_keyboard
from bot.services.cert_checker import CertificateChecker
from bot.handlers.admin import is_admin


async def check_p12_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for"] = "check_p12_file"
    context.user_data.pop("check_p12_temp_path", None)

    msg_text = (
        "🔍 **Check Certificate (P12 Inspection)**\n\n"
        "Send the `.p12` file you want to test and inspect.\n"
        "I will check:\n"
        "• Common Name & Team ID\n"
        "• Expiration Date & Days Remaining\n"
        "• Validity Status & Private Key presence\n\n"
        "📎 *Please upload the `.p12` file as a document:* "
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            msg_text, reply_markup=get_cancel_keyboard(), parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            msg_text, reply_markup=get_cancel_keyboard(), parse_mode="Markdown"
        )


async def process_check_p12_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ Please send a valid `.p12` file document.")
        return

    if not doc.file_name.lower().endswith((".p12", ".pfx")):
        await update.message.reply_text("❌ The uploaded file is not a `.p12` or `.pfx` certificate. Please upload a valid certificate.")
        return

    temp_p12 = os.path.join(TEMP_DIR, f"check_{update.effective_user.id}_{doc.file_name}")
    file_obj = await doc.get_file()
    await file_obj.download_to_drive(temp_p12)

    context.user_data["check_p12_temp_path"] = temp_p12
    context.user_data["waiting_for"] = "check_p12_password"

    await update.message.reply_text(
        "🔑 **Enter the password for this `.p12` certificate:**\n\n"
        "(If there is no password, send `none` or `blank`)",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )


async def process_check_p12_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    main_keyboard = get_main_keyboard(is_admin=is_admin(user))
    password = update.message.text.strip()
    if password.lower() in ["none", "blank", "empty", "no"]:
        password = ""

    temp_p12 = context.user_data.get("check_p12_temp_path")
    if not temp_p12 or not os.path.exists(temp_p12):
        await update.message.reply_text(
            "❌ Session expired or file not found. Please click `🔍 Check P12` again.",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
        context.user_data.clear()
        return

    info = CertificateChecker.inspect_p12(temp_p12, password)

    try:
        os.remove(temp_p12)
    except Exception:
        pass

    context.user_data.clear()

    if not info.get("success"):
        error_msg = info.get("error", "Unknown error")
        await update.message.reply_text(
            f"❌ **Certificate Inspection Failed**\n\n"
            f"⚠️ **Reason:** `{error_msg}`\n\n"
            "Please check if the password was correct or if the file is corrupted.",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
        return

    status_tag = "🔴 EXPIRED" if info.get("is_expired") else "🟢 ACTIVE & VALID"
    days_left = info.get("days_left", 0)
    days_str = f"{days_left} days remaining" if days_left > 0 else "Expired"

    result_text = (
        f"✅ **Certificate Analysis Report**\n\n"
        f"**Status:** {status_tag}\n\n"
        f"• **Certificate Name:** `{info.get('common_name')}`\n"
        f"• **Team ID / Org:** `{info.get('team_id') or info.get('organization') or 'Apple Developer'}`\n"
        f"• **Valid From:** `{info.get('valid_from')}`\n"
        f"• **Expires On:** `{info.get('valid_to')}`\n"
        f"• **Time Left:** `{days_str}`\n"
        f"• **Private Key Included:** `{'Yes ✅' if info.get('has_private_key') else 'No ❌'}`\n\n"
        "✨ *This certificate can be used to sign IPA files!*"
    )

    await update.message.reply_text(
        result_text,
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )
