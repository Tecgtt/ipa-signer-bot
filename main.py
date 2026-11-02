import logging
import sys
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from config import BOT_TOKEN
from bot.handlers.start import start_handler
from bot.handlers.dispatcher import text_router, document_router, photo_router, callback_router
from bot.handlers.admin import admin_dashboard_handler
from bot.services.web_server import start_web_server

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update, context):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


async def post_init(application):
    # Launch built-in web server for large file (>2GB) downloads
    await start_web_server()


def main():
    if not BOT_TOKEN:
        print("\n" + "=" * 60)
        print("❌ ERROR: BOT_TOKEN is missing!")
        print("=" * 60 + "\n")
        sys.exit(1)

    print("🚀 Initializing iOS IPA Signer Telegram Bot...")
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("admin", admin_dashboard_handler))

    # Callback queries (Inline buttons)
    app.add_handler(CallbackQueryHandler(callback_router))

    # Text messages (Menu buttons & text input)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    # Documents (.ipa, .p12, .mobileprovision, .dylib)
    app.add_handler(MessageHandler(filters.Document.ALL, document_router))

    # Photos (Thumbnails / App icons)
    app.add_handler(MessageHandler(filters.PHOTO, photo_router))

    # Error handling
    app.add_error_handler(error_handler)

    print("✅ Bot is online and listening for messages!")
    app.run_polling()


if __name__ == "__main__":
    main()
