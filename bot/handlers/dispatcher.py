import os
from telegram import Update
from telegram.ext import ContextTypes
from config import CERTS_DIR, DATA_DIR
from bot.keyboards import get_main_keyboard, get_cancel_keyboard, get_cert_save_keyboard, get_cert_menu_keyboard, get_p12_password_keyboard
from bot.services.database import db
from bot.services.cert_checker import CertificateChecker
from bot.handlers.sign_ipa import sign_ipa_start, process_ipa_input
from bot.handlers.certificate import my_certificate_menu
from bot.handlers.check_p12 import check_p12_prompt, process_check_p12_file, process_check_p12_password
from bot.handlers.thumbnail import thumbnail_menu, process_thumbnail_upload
from bot.handlers.settings import settings_menu
from bot.handlers.admin import admin_dashboard_handler, handle_admin_callback, process_admin_broadcast, is_admin


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    waiting_for = context.user_data.get("waiting_for")
    user = update.effective_user
    admin_flag = is_admin(user)
    main_keyboard = get_main_keyboard(is_admin=admin_flag)

    # 1. Main menu reply keyboard buttons
    if text == "📲 Sign IPA":
        context.user_data.clear()
        await sign_ipa_start(update, context)
        return
    elif text == "📦 My Certificate":
        context.user_data.clear()
        await my_certificate_menu(update, context)
        return
    elif text == "🔍 Check P12":
        context.user_data.clear()
        await check_p12_prompt(update, context)
        return
    elif text == "🖼️ Change Thumbnail":
        context.user_data.clear()
        await thumbnail_menu(update, context)
        return
    elif text == "⚙️ Settings":
        context.user_data.clear()
        await settings_menu(update, context)
        return
    elif text == "👑 Admin Dashboard":
        context.user_data.clear()
        await admin_dashboard_handler(update, context)
        return

    # 2. Check active conversation states
    if waiting_for == "sign_ipa_input":
        await process_ipa_input(update, context)
        return

    elif waiting_for == "check_p12_password":
        await process_check_p12_password(update, context)
        return

    elif waiting_for == "admin_broadcast_text":
        await process_admin_broadcast(update, context)
        return

    elif waiting_for == "p12_password":
        pwd = text
        if pwd.lower() in ["none", "blank", "empty", "no", "skip"]:
            pwd = ""

        user_id = user.id
        p12_path = os.path.join(CERTS_DIR, f"{user_id}.p12")

        if os.path.exists(p12_path):
            info = CertificateChecker.inspect_p12(p12_path, pwd)
            if not info.get("success"):
                await update.message.reply_text(
                    f"❌ **गलत पासवर्ड! (Invalid Password)**\n\n"
                    f"`{info.get('error')}`\n\n"
                    "👉 कृपया अपने `.p12` का सही पासवर्ड फिर से दर्ज करें:",
                    reply_markup=get_p12_password_keyboard(),
                    parse_mode="Markdown"
                )
                return

            # Password is valid! Save it permanently to DB!
            db.update_user_fields(
                user_id,
                p12_path=p12_path,
                p12_password=pwd,
                cert_name=info.get("common_name", "Saved Certificate"),
                cert_expiry=info.get("valid_to", "Active")
            )

            # Check if mobileprovision already exists
            prov_path = os.path.join(CERTS_DIR, f"{user_id}.mobileprovision")
            has_prov = os.path.exists(prov_path)

            if not has_prov:
                context.user_data["waiting_for"] = "upload_prov"
                await update.message.reply_text(
                    f"✅ **.p12 और पासवर्ड सुरक्षित सेव हो गया!**\n\n"
                    f"• **Cert:** `{info.get('common_name')}`\n"
                    f"• **Expires:** `{info.get('valid_to')}`\n\n"
                    "📤 **अब अपनी `.mobileprovision` फ़ाइल भेजें:**",
                    reply_markup=get_cancel_keyboard(),
                    parse_mode="Markdown"
                )
            else:
                context.user_data.pop("waiting_for", None)
                pinfo = CertificateChecker.inspect_mobileprovision(prov_path)
                prov_name = pinfo.get("name") or "Valid Profile"
                await update.message.reply_text(
                    "🎉 **सर्टिफिकेट और प्रोफाइल सफलतापूर्वक सेव हो गया!**\n\n"
                    f"• **P12 Cert:** `{info.get('common_name')}`\n"
                    f"• **Profile:** `{prov_name}`\n"
                    "• **Storage:** हमेशा के लिए सुरक्षित सेव है ✅\n\n"
                    "👉 अब सीधे नीचे **`📲 Sign & Direct Install IPA`** बटन दबाएं!",
                    reply_markup=main_keyboard,
                    parse_mode="Markdown"
                )
        return

    elif waiting_for == "set_bundle_id":
        new_bundle = text
        if new_bundle.lower() in ["default", "original", "none", "clear"]:
            new_bundle = ""
        db.update_user_fields(user.id, custom_bundle_id=new_bundle)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ **Bundle ID Updated to:** `{new_bundle or 'Default (Original)'}`",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
        return

    elif waiting_for == "set_app_name":
        new_name = text
        if new_name.lower() in ["default", "original", "none", "clear"]:
            new_name = ""
        db.update_user_fields(user.id, custom_app_name=new_name)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ **App Display Name Updated to:** `{new_name or 'Default (Original)'}`",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
        return

    elif waiting_for == "upload_dylib":
        if text.lower() in ["none", "clear", "remove"]:
            db.update_user_fields(user.id, inject_dylib_path="")
            context.user_data.pop("waiting_for", None)
            await update.message.reply_text(
                "✅ **Dylib injection cleared.**",
                reply_markup=main_keyboard,
                parse_mode="Markdown"
            )
            return

    # Default fallback
    await update.message.reply_text(
        "👋 Please select an option from the menu below:",
        reply_markup=main_keyboard
    )


async def document_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    waiting_for = context.user_data.get("waiting_for")
    doc = update.message.document
    filename = (doc.file_name or "").lower()
    user = update.effective_user
    user_id = user.id
    main_keyboard = get_main_keyboard(is_admin=is_admin(user))

    # 1. P12 Certificate (.p12, .pfx) - ALWAYS TOP PRIORITY
    if filename.endswith((".p12", ".pfx")) or waiting_for == "upload_p12":
        target = os.path.join(CERTS_DIR, f"{user_id}.p12")
        file_obj = await doc.get_file()
        await file_obj.download_to_drive(target)
        db.update_user_fields(user_id, p12_path=target)

        # IMMEDIATELY ASK FOR P12 PASSWORD!
        context.user_data["waiting_for"] = "p12_password"
        await update.message.reply_text(
            "✅ **.p12 फ़ाइल प्राप्त हुई!**\n\n"
            "🔑 **अब अपने `.p12` सर्टिफ़िकेट का पासवर्ड दर्ज करें:**\n"
            "(यदि कोई पासवर्ड नहीं है, तो नीचे 'No Password' दबाएं या `none` लिखें)",
            reply_markup=get_p12_password_keyboard(),
            parse_mode="Markdown"
        )
        return

    # 2. Mobileprovision Profile (.mobileprovision, .provisionprofile) - ALWAYS TOP PRIORITY
    elif filename.endswith((".mobileprovision", ".provisionprofile")) or waiting_for == "upload_prov":
        target = os.path.join(CERTS_DIR, f"{user_id}.mobileprovision")
        file_obj = await doc.get_file()
        await file_obj.download_to_drive(target)
        db.update_user_fields(user_id, mobileprovision_path=target)

        p12_path = os.path.join(CERTS_DIR, f"{user_id}.p12")
        user_data = db.get_user(user_id) or {}
        has_p12 = os.path.exists(p12_path)
        p12_pass = user_data.get("p12_password")

        if not has_p12:
            context.user_data["waiting_for"] = "upload_p12"
            await update.message.reply_text(
                "✅ **.mobileprovision फ़ाइल प्राप्त हुई!**\n\n"
                "📤 **अब अपनी `.p12` सर्टिफ़िकेट फ़ाइल भेजें:**",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown"
            )
        elif p12_pass is None:
            context.user_data["waiting_for"] = "p12_password"
            await update.message.reply_text(
                "✅ **.mobileprovision प्राप्त हुई!**\n\n"
                "🔑 **अब अपने `.p12` सर्टिफ़िकेट का पासवर्ड दर्ज करें:**\n"
                "(यदि कोई पासवर्ड नहीं है, तो 'No Password' दबाएं या `none` लिखें)",
                reply_markup=get_p12_password_keyboard(),
                parse_mode="Markdown"
            )
        else:
            context.user_data.pop("waiting_for", None)
            pinfo = CertificateChecker.inspect_mobileprovision(target)
            await update.message.reply_text(
                "🎉 **सर्टिफिकेट और प्रोफाइल सफलतापूर्वक सेव हो गया!**\n\n"
                f"• **P12 Cert:** `{user_data.get('cert_name') or 'Configured'}`\n"
                f"• **Profile:** `{pinfo.get('name') or 'Configured'}`\n"
                "• **Storage:** हमेशा के लिए सुरक्षित सेव है ✅\n\n"
                "👉 अब सीधे नीचे **`📲 Sign & Direct Install IPA`** बटन दबाएं!",
                reply_markup=main_keyboard,
                parse_mode="Markdown"
            )
        return

    # 3. ZIP check: extract .p12 and .mobileprovision if user sends a zip
    elif filename.endswith(".zip") and waiting_for != "sign_ipa_input":
        import zipfile
        temp_zip = os.path.join(TEMP_DIR, f"cert_{user_id}.zip")
        file_obj = await doc.get_file()
        await file_obj.download_to_drive(temp_zip)
        found_p12, found_prov = False, False
        try:
            with zipfile.ZipFile(temp_zip, 'r') as z:
                for zname in z.namelist():
                    zlow = zname.lower()
                    if zlow.endswith((".p12", ".pfx")) and not found_p12:
                        p12_target = os.path.join(CERTS_DIR, f"{user_id}.p12")
                        with open(p12_target, "wb") as pf:
                            pf.write(z.read(zname))
                        db.update_user_fields(user_id, p12_path=p12_target)
                        found_p12 = True
                    elif zlow.endswith((".mobileprovision", ".provisionprofile")) and not found_prov:
                        prov_target = os.path.join(CERTS_DIR, f"{user_id}.mobileprovision")
                        with open(prov_target, "wb") as mf:
                            mf.write(z.read(zname))
                        db.update_user_fields(user_id, mobileprovision_path=prov_target)
                        found_prov = True
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
        except Exception:
            pass

        if found_p12 or found_prov:
            cert_info = db.get_user_cert_info(user_id)
            if cert_info["is_ready"]:
                context.user_data["waiting_for"] = "p12_password"
                await update.message.reply_text(
                    "✅ **ZIP से सर्टिफ़िकेट और प्रोफाइल दोनों निकाल लिए गए हैं!**\n\n"
                    "👇 नीचे **'Save Certificate'** दबाकर सुरक्षित सेव करें:",
                    reply_markup=get_cert_save_keyboard(),
                    parse_mode="Markdown"
                )
                return

    # 4. Check P12 inspection tool
    elif waiting_for == "check_p12_file":
        await process_check_p12_file(update, context)
        return

    # 5. Check if user is signing an IPA
    elif waiting_for == "sign_ipa_input" or filename.endswith(".ipa"):
        await process_ipa_input(update, context)
        return

    elif waiting_for == "upload_thumbnail" or filename.endswith((".png", ".jpg", ".jpeg")):
        await process_thumbnail_upload(update, context)
        return

    elif waiting_for == "upload_dylib" or filename.endswith((".dylib", ".deb")):
        dylibs_dir = os.path.join(DATA_DIR, "dylibs")
        os.makedirs(dylibs_dir, exist_ok=True)
        target = os.path.join(dylibs_dir, f"{user_id}_{doc.file_name}")
        file_obj = await doc.get_file()
        await file_obj.download_to_drive(target)

        db.update_user_fields(user_id, inject_dylib_path=target)
        context.user_data.pop("waiting_for", None)

        await update.message.reply_text(
            f"✅ **Tweak / Dylib saved!** (`{doc.file_name}`)\nIt will be injected into future signed IPAs.",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        "📄 File received. If you want to sign an IPA, click `📲 Sign IPA` first.",
        reply_markup=main_keyboard
    )


async def photo_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    main_keyboard = get_main_keyboard(is_admin=is_admin(user))
    waiting_for = context.user_data.get("waiting_for")
    if waiting_for == "upload_thumbnail":
        await process_thumbnail_upload(update, context)
    else:
        await update.message.reply_text(
            "📷 Image received! If you want to use it as an app icon, click `🖼️ Change Thumbnail`.",
            reply_markup=main_keyboard
        )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = update.effective_user
    main_keyboard = get_main_keyboard(is_admin=is_admin(user))

    if data == "action_cancel":
        context.user_data.clear()
        await query.answer()
        await query.message.reply_text("❌ Action cancelled.", reply_markup=main_keyboard)
        return

    elif data == "menu_home":
        context.user_data.clear()
        await query.answer()
        await query.message.reply_text("🏠 Main Menu", reply_markup=main_keyboard)
        return

    elif data.startswith("cert_"):
        from bot.handlers.certificate import handle_cert_callback
        await handle_cert_callback(update, context)

    elif data.startswith("thumb_"):
        from bot.handlers.thumbnail import handle_thumbnail_callback
        await handle_thumbnail_callback(update, context)

    elif data.startswith("settings_"):
        from bot.handlers.settings import handle_settings_callback
        await handle_settings_callback(update, context)

    elif data.startswith("admin_"):
        await handle_admin_callback(update, context)
