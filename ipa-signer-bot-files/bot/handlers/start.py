from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards import get_main_keyboard
from bot.services.database import db
from bot.handlers.admin import is_admin


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.create_or_update_user(user.id, user.username or "", user.first_name or "")
    
    # Clear any active user state
    context.user_data.clear()

    admin_status = is_admin(user)
    reply_markup = get_main_keyboard(is_admin=admin_status)

    welcome_text = (
        f"👋 **Hello {user.first_name}! Welcome to the iOS IPA Signer Bot.**\n\n"
        "⚡ **Features:**\n"
        "• 📲 **Sign IPA**: Sign any iOS IPA file with your certificate (supports >2GB)\n"
        "• 📦 **My Certificate**: Manage your `.p12` & `.mobileprovision`\n"
        "• 🔍 **Check P12**: Check certificate validity, expiry, and team info\n"
        "• 🖼️ **Change Thumbnail**: Customize the app icon before signing\n"
        "• ⚙️ **Settings**: Modify Bundle ID, App Name & Inject Dylibs\n\n"
        "👇 *Please select an option from the menu below to get started:*"
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
