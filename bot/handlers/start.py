from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards import get_main_keyboard
from bot.services.database import db
from bot.handlers.admin import is_admin


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.create_or_update_user(user.id, user.username or "", user.first_name or "")
    context.user_data.clear()

    reply_markup = get_main_keyboard(is_admin=is_admin(user))

    welcome_text = (
        f"👋 **Welcome {user.first_name}!**\n\n"
        "⚡ **Fast iOS IPA Signer Bot (2GB Support)**\n\n"
        "👇 नीचे दिए गए मेन्यू से विकल्प चुनें:"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
