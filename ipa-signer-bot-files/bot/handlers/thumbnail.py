import os
from telegram import Update
from telegram.ext import ContextTypes
from config import ICONS_DIR
from bot.keyboards import get_thumbnail_keyboard, get_cancel_keyboard, get_main_keyboard
from bot.services.database import db
from bot.handlers.admin import is_admin


async def thumbnail_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id) or {}
    icon_path = user_data.get("custom_icon_path")

    has_icon = bool(icon_path and os.path.exists(icon_path))
    status_text = "✅ Custom Thumbnail Active" if has_icon else "⚪ Using Default Original IPA Icon"

    text = (
        f"🖼️ **App Thumbnail / Icon Changer**\n\n"
        f"**Current Status:** {status_text}\n\n"
        "You can customize the iOS app icon of your signed IPA file.\n"
        "When enabled, your chosen image will replace the app icon inside the IPA automatically during signing.\n\n"
        "💡 *Recommended format: Square PNG or JPG (e.g. 512x512 or 1024x1024)*"
    )

    reply_markup = get_thumbnail_keyboard(has_thumbnail=has_icon)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_thumbnail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    user_id = user.id

    if data == "thumb_upload":
        context.user_data["waiting_for"] = "upload_thumbnail"
        await query.message.reply_text(
            "🖼️ **Please send the image you want to use as the app thumbnail.**\n\n"
            "You can send it as a photo or as a PNG/JPG document.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "thumb_remove":
        db.clear_thumbnail(user_id)
        main_keyboard = get_main_keyboard(is_admin=is_admin(user))
        await query.message.reply_text(
            "🗑️ **Custom thumbnail removed.** Future signed IPAs will retain their original app icons.",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )


async def process_thumbnail_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    target_path = os.path.join(ICONS_DIR, f"{user_id}.png")

    file_obj = None
    if update.message.photo:
        photo = update.message.photo[-1]
        file_obj = await photo.get_file()
    elif update.message.document:
        doc = update.message.document
        if doc.mime_type and doc.mime_type.startswith("image/"):
            file_obj = await doc.get_file()
        elif doc.file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            file_obj = await doc.get_file()

    if not file_obj:
        await update.message.reply_text(
            "❌ Please upload a valid image file (PNG, JPG).",
            reply_markup=get_cancel_keyboard()
        )
        return

    await file_obj.download_to_drive(target_path)
    db.update_user_fields(user_id, custom_icon_path=target_path)
    context.user_data.pop("waiting_for", None)

    main_keyboard = get_main_keyboard(is_admin=is_admin(user))

    await update.message.reply_text(
        "✅ **Custom Thumbnail Saved Successfully!**\n\n"
        "This icon will now be injected into your signed IPAs.\n"
        "You can sign an IPA now using `📲 Sign IPA`.",
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )
