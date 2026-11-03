import os
from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards import get_cert_menu_keyboard, get_cert_delete_confirm_keyboard, get_cert_save_keyboard, get_cancel_keyboard, get_main_keyboard
from bot.services.database import db
from bot.services.cert_checker import CertificateChecker


async def my_certificate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cert_info = db.get_user_cert_info(user_id)

    is_ready = cert_info["is_ready"]
    cert_name = cert_info.get("cert_name") or "Saved Certificate"
    cert_expiry = cert_info.get("cert_expiry") or "Active"

    if is_ready:
        text = (
            "📦 **My Certificate**\n\n"
            "• **Status:** Saved ✅\n"
            f"• **Name:** `{cert_name}`\n"
            f"• **Expires:** `{cert_expiry}`\n\n"
            "*(सर्टिफिकेट परमानेंटली सुरक्षित है)*"
        )
    else:
        text = (
            "📦 **My Certificate**\n\n"
            "• **Status:** ❌ Missing\n"
            "Please upload your `.p12` file below."
        )

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
    user_id = update.effective_user.id

    if data == "cert_sign_now":
        from bot.handlers.sign_ipa import sign_ipa_start
        context.user_data.clear()
        await sign_ipa_start(update, context)
        return

    elif data == "cert_save_direct":
        cert_info = db.get_user_cert_info(user_id)
        p12_path = cert_info.get("p12_path")
        prov_path = cert_info.get("mobileprovision_path")
        pwd = cert_info.get("p12_password", "")

        info = CertificateChecker.inspect_p12(p12_path, pwd) if p12_path and os.path.exists(p12_path) else {}
        cert_name = info.get("common_name") or "Saved Certificate"
        cert_expiry = info.get("valid_to") or "Active"

        db.update_user_fields(
            user_id,
            p12_path=p12_path,
            mobileprovision_path=prov_path,
            cert_name=cert_name,
            cert_expiry=cert_expiry
        )
        context.user_data.clear()

        await query.message.edit_text(
            f"💾 **Certificate Saved Permanently!**\n\n"
            f"• **Name:** `{cert_name}`\n"
            f"• **Expires:** `{cert_expiry}`\n"
            "• **Status:** हमेशा के लिए सुरक्षित सेव हो चुका है ✅\n\n"
            "👉 अब सीधे नीचे `📲 Sign & Direct Install IPA` दबाएं!",
            reply_markup=get_cert_menu_keyboard(has_cert=True),
            parse_mode="Markdown"
        )
        return

    elif data == "cert_no_password":
        from config import CERTS_DIR
        p12_path = os.path.join(CERTS_DIR, f"{user_id}.p12")
        if not os.path.exists(p12_path):
            await query.message.reply_text("❌ `.p12` फ़ाइल नहीं मिली। कृपया `.p12` फ़ाइल भेजें।")
            return

        info = CertificateChecker.inspect_p12(p12_path, "")
        if not info.get("success"):
            context.user_data["waiting_for"] = "p12_password"
            await query.message.reply_text(
                "⚠️ **इस `.p12` में पासवर्ड लगा हुआ है!**\n\n"
                "👉 कृपया चैट में अपना सही पासवर्ड टाइप करके भेजें:",
                parse_mode="Markdown"
            )
            return

        db.update_user_fields(
            user_id,
            p12_path=p12_path,
            p12_password="",
            cert_name=info.get("common_name", ""),
            cert_expiry=info.get("valid_to", "")
        )

        prov_path = os.path.join(CERTS_DIR, f"{user_id}.mobileprovision")
        if not os.path.exists(prov_path):
            context.user_data["waiting_for"] = "upload_prov"
            await query.message.edit_text(
                f"✅ **.p12 (बिना पासवर्ड) सेव हो गया!**\n\n"
                f"• **Cert:** `{info.get('common_name')}`\n\n"
                "📤 **अब अपनी `.mobileprovision` फ़ाइल भेजें:**",
                parse_mode="Markdown"
            )
        else:
            context.user_data.pop("waiting_for", None)
            pinfo = CertificateChecker.inspect_mobileprovision(prov_path)
            await query.message.edit_text(
                "🎉 **सर्टिफिकेट और प्रोफाइल सफलतापूर्वक सेव हो गया!**\n\n"
                f"• **P12 Cert:** `{info.get('common_name')}`\n"
                f"• **Profile:** `{pinfo.get('name') or 'Configured'}`\n"
                "• **Storage:** हमेशा के लिए सुरक्षित सेव है ✅\n\n"
                "👉 अब सीधे नीचे **`📲 Sign & Direct Install IPA`** बटन दबाएं!",
                reply_markup=get_cert_menu_keyboard(has_cert=True),
                parse_mode="Markdown"
            )
        return

    elif data == "cert_upload_p12":
        context.user_data["waiting_for"] = "upload_p12"
        await query.message.reply_text(
            "📤 **Send your `.p12` certificate file:**",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_upload_prov":
        context.user_data["waiting_for"] = "upload_prov"
        await query.message.reply_text(
            "📤 **Send your `.mobileprovision` file:**",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_set_pass":
        context.user_data["waiting_for"] = "p12_password"
        await query.message.reply_text(
            "🔑 **Enter `.p12` password (send `none` if empty):**",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_delete_ask":
        await query.message.edit_text(
            "⚠️ **Delete Certificate?**\n\nAre you sure you want to delete your saved certificate?",
            reply_markup=get_cert_delete_confirm_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "cert_delete_confirm":
        db.clear_certificate(user_id)
        await query.message.edit_text(
            "🗑️ **Certificate Deleted!**\nYou can now upload a new certificate anytime.",
            parse_mode="Markdown"
        )

    elif data == "cert_menu_home":
        await my_certificate_menu(update, context)
