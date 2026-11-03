import os
from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards import get_cert_menu_keyboard, get_cert_delete_confirm_keyboard, get_cancel_keyboard, get_main_keyboard
from bot.services.database import db
from bot.services.cert_checker import CertificateChecker
from bot.handlers.admin import is_admin


async def my_certificate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cert_info = db.get_user_cert_info(user_id)

    has_p12 = cert_info["has_p12"]
    has_prov = cert_info["has_prov"]
    p12_pass = cert_info["p12_password"]
    cert_name = cert_info["cert_name"] or "Custom"
    cert_expiry = cert_info["cert_expiry"] or "Unknown"

    has_pass = bool(p12_pass is not None and p12_pass != "")

    p12_status = "✅ Active & Saved" if has_p12 else "❌ Missing"
    prov_status = "✅ Active & Saved" if has_prov else "❌ Missing"
    pass_status = "✅ Configured" if has_pass else ("⚠️ Empty / None" if has_p12 else "❌ Missing")

    is_ready = cert_info["is_ready"]

    if is_ready:
        status_line = "🟢 **Status:** 100% Ready (Permanently Saved ✅)\n*(जब तक आप डिलीट नहीं करेंगे, यह हमेशा सेव रहेगा)*"
    else:
        status_line = "🟡 **Status:** Incomplete (Certificate files required)"

    text = (
        f"📦 **Certificate Management**\n\n"
        f"{status_line}\n\n"
        f"• **P12 Certificate:** {p12_status}\n"
        f"• **Provisioning Profile:** {prov_status}\n"
        f"• **P12 Password:** {pass_status}\n\n"
    )

    if has_p12 and cert_name and cert_name != "Custom":
        text += (
            f"**Certificate Details:**\n"
            f"• **Name:** `{cert_name}`\n"
            f"• **Expires:** `{cert_expiry}`\n\n"
        )

    if has_prov:
        prov_info = CertificateChecker.inspect_mobileprovision(cert_info["mobileprovision_path"])
        if prov_info.get("success"):
            text += (
                f"**Provision Profile Details:**\n"
                f"• **Profile:** `{prov_info.get('name')}`\n"
                f"• **Team:** `{prov_info.get('team_name')} ({prov_info.get('team_id')})`\n"
                f"• **App ID:** `{prov_info.get('app_id')}`\n"
                f"• **Devices:** `{prov_info.get('devices_count')} devices` "
                f"({'Enterprise' if prov_info.get('is_enterprise') else 'Development/AdHoc'})\n\n"
            )

    text += "Use the buttons below to manage your certificate:"

    reply_markup = get_cert_menu_keyboard(has_cert=is_ready)
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

    if data == "cert_sign_now":
        from bot.handlers.sign_ipa import sign_ipa_start
        context.user_data.clear()
        await sign_ipa_start(update, context)
        return

    elif data == "cert_upload_p12":
        context.user_data["waiting_for"] = "upload_p12"
        await query.message.reply_text(
            "📤 **Step 1/3: Send your `.p12` certificate file:**\n\n"
            "Please send it as a document/file attachment here in chat.\n"
            "(After this, I will automatically ask for your `.mobileprovision` file)",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_upload_prov":
        context.user_data["waiting_for"] = "upload_prov"
        await query.message.reply_text(
            "📤 **Send your `.mobileprovision` file:**\n\n"
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

    elif data == "cert_delete_ask":
        await query.message.edit_text(
            "⚠️ **Delete Certificate Confirmation**\n\n"
            "क्या आप वाकई अपना परमानेंटली सेव किया हुआ सर्टिफिकेट डिलीट करना चाहते हैं?\n\n"
            "डिलीट करने के बाद जब तक आप नया सर्टिफिकेट अपलोड नहीं करेंगे, आप IPA साइन नहीं कर पाएंगे।",
            reply_markup=get_cert_delete_confirm_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_delete_confirm":
        db.clear_certificate(user_id)
        main_keyboard = get_main_keyboard(is_admin=is_admin(user))
        await query.message.edit_text(
            "🗑️ **Certificate Deleted Successfully!**\n\n"
            "आपका सर्टिफिकेट और प्रोविज़निंग प्रोफाइल स्थायी रूप से हटा दिया गया है।\n"
            "जब आप नया सर्टिफिकेट अपलोड करेंगे, तब वह दोबारा हमेशा के लिए सेव हो जाएगा।",
            parse_mode="Markdown"
        )

    elif data == "cert_menu_home":
        await my_certificate_menu(update, context)
