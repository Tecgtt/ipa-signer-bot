import os
from telegram import Update
from telegram.ext import ContextTypes
from config import DATA_DIR
from bot.keyboards import get_settings_keyboard, get_cancel_keyboard, get_main_keyboard
from bot.services.database import db
from bot.handlers.admin import is_admin


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id) or {}

    bundle_id = user_data.get("custom_bundle_id") or ""
    app_name = user_data.get("custom_app_name") or ""
    dylib_path = user_data.get("inject_dylib_path") or ""
    dylib_display = os.path.basename(dylib_path) if (dylib_path and os.path.exists(dylib_path)) else "None"

    text = (
        "⚙️ **Signing Settings & Preferences**\n\n"
        "Configure custom properties for your signed IPA files:\n\n"
        f"• **Bundle ID:** `{bundle_id if bundle_id else 'Original'}`\n"
        f"• **App Name:** `{app_name if app_name else 'Original'}`\n"
        f"• **Injected Dylib:** `{dylib_display}`\n\n"
        "💡 *Duplicate App Tip:* Changing the Bundle ID allows you to install multiple copies of the same app on your iOS device!"
    )

    reply_markup = get_settings_keyboard(bundle_id, app_name)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    user_id = user.id

    if data == "settings_bundle_id":
        context.user_data["waiting_for"] = "set_bundle_id"
        await query.message.reply_text(
            "🆔 **Set Custom Bundle Identifier**\n\n"
            "Send the new bundle ID you want to assign (e.g. `com.myapp.clone` or `com.twitter.custom`).\n"
            "To reset to original, send `default` or `original`.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "settings_app_name":
        context.user_data["waiting_for"] = "set_app_name"
        await query.message.reply_text(
            "✏️ **Set Custom App Name**\n\n"
            "Send the custom display name that will show under the app icon on your iOS home screen.\n"
            "To reset to original, send `default` or `original`.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "settings_dylib":
        context.user_data["waiting_for"] = "upload_dylib"
        await query.message.reply_text(
            "💉 **Inject Dylib / Tweak**\n\n"
            "Please send the `.dylib` or `.deb` tweak file you want injected into the IPA.\n"
            "To clear any existing dylib, send `none`.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "settings_reset":
        db.update_user_fields(
            user_id,
            custom_bundle_id="",
            custom_app_name="",
            inject_dylib_path=""
        )
        main_keyboard = get_main_keyboard(is_admin=is_admin(user))
        await query.message.reply_text(
            "🔄 **Settings have been reset to defaults.**",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
