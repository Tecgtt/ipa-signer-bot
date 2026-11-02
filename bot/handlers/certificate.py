import os
from telegram import Update
from telegram.ext import ContextTypes
from config import CERTS_DIR
from bot.keyboards import get_cert_menu_keyboard, get_cancel_keyboard, get_main_keyboard
from bot.services.database import db
from bot.services.cert_checker import CertificateChecker
from bot.handlers.admin import is_admin


async def my_certificate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id) or {}

    p12_path = user_data.get("p12_path")
    prov_path = user_data.get("mobileprovision_path")
    p12_pass = user_data.get("p12_password")
    cert_name = user_data.get("cert_name") or "Not configured"
    cert_expiry = user_data.get("cert_expiry") or "Unknown"

    has_p12 = p12_path and os.path.exists(p12_path)
    has_prov = prov_path and os.path.exists(prov_path)
    has_pass = bool(p12_pass is not None and p12_pass != "")

    p12_status = "✅ Uploaded" if has_p12 else "❌ Missing"
    prov_status = "✅ Uploaded" if has_prov else "❌ Missing"
    pass_status = "✅ Set" if has_pass else ("⚠️ Empty / None" if has_p12 else "❌ Missing")

    status_emoji = "🟢 Ready" if (has_p12 and has_prov) else "🟡 Incomplete"

    text = (
        f"📦 **Certificate Management**\n\n"
        f"**Status:** {status_emoji}\n\n"
        f"• **P12 Certificate:** {p12_status}\n"
        f"• **Provisioning Profile:** {prov_status}\n"
        f"• **P12 Password:** {pass_status}\n\n"
    )

    if has_p12 and cert_name != "Not configured":
        text += (
            f"**Certificate Details:**\n"
            f"• **Name:** `{cert_name}`\n"
            f"• **Expires:** `{cert_expiry}`\n\n"
        )

    if has_prov:
        prov_info = CertificateChecker.inspect_mobileprovision(prov_path)
        if prov_info.get("success"):
            text += (
                f"**Provision Profile Details:**\n"
                f"• **Profile:** `{prov_info.get('name')}`\n"
                f"• **Team:** `{prov_info.get('team_name')} ({prov_info.get('team_id')})`\n"
                f"• **App ID:** `{prov_info.get('app_id')}`\n"
                f"• **Devices:** `{prov_info.get('devices_count')} devices` "
                f"({'Enterprise' if prov_info.get('is_enterprise') else 'Development/AdHoc'})\n\n"
            )

    text += "Use the buttons below to upload or update your certificate files:"

    reply_markup = get_cert_menu_keyboard(has_cert=(has_p12 or has_prov))
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_cert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    user_id = user.id

    if data == "cert_upload_p12":
        context.user_data["waiting_for"] = "upload_p12"
        await query.message.reply_text(
            "📤 **Send your `.p12` certificate file now.**\n\n"
            "Please send it as a document/file attachment in Telegram.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_upload_prov":
        context.user_data["waiting_for"] = "upload_prov"
        await query.message.reply_text(
            "📤 **Send your `.mobileprovision` file now.**\n\n"
            "Please send it as a document/file attachment in Telegram.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_set_pass":
        context.user_data["waiting_for"] = "p12_password"
        await query.message.reply_text(
            "🔑 **Please send the password for your `.p12` certificate.**\n\n"
            "If your certificate has no password, send `none` or `blank`.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_delete":
        db.clear_certificate(user_id)
        main_keyboard = get_main_keyboard(is_admin=is_admin(user))
        await query.message.reply_text(
            "🗑️ **Your certificate and mobileprovision files have been deleted.**",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
