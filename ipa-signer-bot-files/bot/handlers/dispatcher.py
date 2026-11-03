import os
from telegram import Update
from telegram.ext import ContextTypes
from config import CERTS_DIR, DATA_DIR
from bot.keyboards import get_main_keyboard, get_cancel_keyboard
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
        if pwd.lower() in ["none", "blank", "empty", "no"]:
            pwd = ""

        user_id = user.id
        p12_path = os.path.join(CERTS_DIR, f"{user_id}.p12")

        if os.path.exists(p12_path):
            info = CertificateChecker.inspect_p12(p12_path, pwd)
            if not info.get("success"):
                await update.message.reply_text(
                    f"❌ **Invalid Password!**\n\n`{info.get('error')}`\n\nPlease re-enter the correct password:",
                    reply_markup=get_cancel_keyboard(),
                    parse_mode="Markdown"
                )
                return

            db.update_user_fields(
                user_id,
                p12_password=pwd,
                cert_name=info.get("common_name", ""),
                cert_expiry=info.get("valid_to", "")
            )
            context.user_data.pop("waiting_for", None)

            await update.message.reply_text(
                f"✅ **Password Verified & Certificate Saved!**\n\n"
                f"• **Certificate:** `{info.get('common_name')}`\n"
                f"• **Expires:** `{info.get('valid_to')}`\n\n"
                "You are now ready to sign IPAs! Tap `📲 Sign IPA` to begin.",
                reply_markup=main_keyboard,
                parse_mode="Markdown"
            )
        else:
            db.update_user_fields(user_id, p12_password=pwd)
            context.user_data.pop("waiting_for", None)
            await update.message.reply_text(
                "🔑 **Password saved.** Now please upload your `.p12` file.",
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

    if waiting_for == "sign_ipa_input" or filename.endswith(".ipa"):
        await process_ipa_input(update, context)
        return

    elif waiting_for == "check_p12_file":
        await process_check_p12_file(update, context)
        return

    elif waiting_for == "upload_p12" or filename.endswith((".p12", ".pfx")):
        target = os.path.join(CERTS_DIR, f"{user_id}.p12")
        file_obj = await doc.get_file()
        await file_obj.download_to_drive(target)
        db.update_user_fields(user_id, p12_path=target)

        user_data = db.get_user(user_id) or {}
        p12_pass = user_data.get("p12_password", "")

        info = CertificateChecker.inspect_p12(target, p12_pass)
        if info.get("success"):
            db.update_user_fields(
                user_id,
                cert_name=info.get("common_name", ""),
                cert_expiry=info.get("valid_to", "")
            )
            context.user_data.pop("waiting_for", None)
            await update.message.reply_text(
                f"✅ **P12 Certificate Uploaded & Validated!**\n\n"
                f"• **Certificate Name:** `{info.get('common_name')}`\n"
                f"• **Expires:** `{info.get('valid_to')}`\n"
                f"• **Days Remaining:** `{info.get('days_left')} days`",
                reply_markup=main_keyboard,
                parse_mode="Markdown"
            )
        else:
            context.user_data["waiting_for"] = "p12_password"
            await update.message.reply_text(
                "📥 **`.p12` Certificate uploaded!**\n\n"
                "🔑 Please enter the password for this `.p12` file:\n"
                "(If no password, send `none`)",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown"
            )
        return

    elif waiting_for == "upload_prov" or filename.endswith(".mobileprovision"):
        target = os.path.join(CERTS_DIR, f"{user_id}.mobileprovision")
        file_obj = await doc.get_file()
        await file_obj.download_to_drive(target)
        db.update_user_fields(user_id, mobileprovision_path=target)
        context.user_data.pop("waiting_for", None)

        prov_info = CertificateChecker.inspect_mobileprovision(target)
        if prov_info.get("success"):
            await update.message.reply_text(
                f"✅ **Mobileprovision Profile Uploaded!**\n\n"
                f"• **Profile Name:** `{prov_info.get('name')}`\n"
                f"• **Team:** `{prov_info.get('team_name')} ({prov_info.get('team_id')})`\n"
                f"• **App ID:** `{prov_info.get('app_id')}`\n"
                f"• **Devices:** `{prov_info.get('devices_count')} devices` "
                f"({'Enterprise' if prov_info.get('is_enterprise') else 'AdHoc/Dev'})\n\n"
                "Configuration complete! You can now use `📲 Sign IPA`.",
                reply_markup=main_keyboard,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "✅ **Mobileprovision file uploaded and saved!**",
                reply_markup=main_keyboard
            )
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
