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
import os
import asyncio
import aiohttp
from bot.services.web_server import start_web_server

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update, context):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


async def render_keep_alive():
    """Pings Render external URL every 10 minutes to prevent free tier spin-down/sleep."""
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        return
    target = url.rstrip("/") + "/healthz"
    logger.info(f"🔄 Render Keep-Alive active: {target}")
    while True:
        await asyncio.sleep(600)  # 10 minutes
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(target) as resp:
                    logger.info(f"⏰ Render Keep-Alive ping: {resp.status}")
        except Exception as e:
            logger.warning(f"Render keep-alive ping error: {e}")


async def post_init(application):
    # Launch built-in web server for large file (>2GB) downloads and uploads
    await start_web_server(application.bot)
    # Start keep-alive loop to prevent Render sleep
    asyncio.create_task(render_keep_alive())


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
