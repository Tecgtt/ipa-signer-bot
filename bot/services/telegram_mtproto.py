import os
import time
import asyncio
import logging
from typing import Optional, Callable
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.tl.types import DocumentAttributeFilename
from config import BOT_TOKEN

logger = logging.getLogger(__name__)

# Official public Telegram API credentials (used by open source Telegram apps)
DEFAULT_API_ID = 2040
DEFAULT_API_HASH = "b18441a1ff607e10a989891a5462e627"

API_ID = int(os.getenv("TELEGRAM_API_ID", str(DEFAULT_API_ID)))
API_HASH = os.getenv("TELEGRAM_API_HASH", DEFAULT_API_HASH)

_mtproto_client: Optional[TelegramClient] = None
_client_lock = asyncio.Lock()


async def get_mtproto_client() -> Optional[TelegramClient]:
    """Returns the singleton Telethon MTProto client, initializing if needed."""
    global _mtproto_client
    if _mtproto_client is not None and _mtproto_client.is_connected():
        return _mtproto_client

    async with _client_lock:
        if _mtproto_client is not None and _mtproto_client.is_connected():
            return _mtproto_client

        if not BOT_TOKEN:
            logger.warning("MTProto client: BOT_TOKEN is empty, cannot initialize.")
            return None

        try:
            logger.info("📡 Connecting Telethon MTProto client for up to 2GB in-chat transfers...")
            # Use MemorySession so no database lock or file permission issues occur
            client = TelegramClient(MemorySession(), API_ID, API_HASH)
            await client.start(bot_token=BOT_TOKEN)
            if client.is_connected():
                _mtproto_client = client
                logger.info("✅ Telethon MTProto client connected! 2GB direct in-chat transfers active.")
                return _mtproto_client
        except Exception as e:
            logger.error(f"❌ Failed to start Telethon MTProto client: {e}")
            return None

    return None


async def stop_mtproto_client():
    """Disconnects the MTProto client gracefully."""
    global _mtproto_client
    if _mtproto_client is not None and _mtproto_client.is_connected():
        try:
            await _mtproto_client.disconnect()
            logger.info("Telethon MTProto client disconnected.")
        except Exception as e:
            logger.warning(f"Error disconnecting MTProto client: {e}")
        finally:
            _mtproto_client = None


async def download_direct_media(
    chat_id: int,
    message_id: int,
    dest_path: str,
    progress_fn: Optional[Callable] = None
) -> bool:
    """
    Downloads any media up to 2GB directly from a Telegram message via MTProto.
    """
    client = await get_mtproto_client()
    if not client:
        logger.warning("MTProto client not available for direct download.")
        return False

    try:
        msg = await client.get_messages(chat_id, ids=message_id)
        if not msg or not msg.media:
            logger.warning(f"No media found in message {message_id} in chat {chat_id}")
            return False

        logger.info(f"Starting direct MTProto download for message {message_id} -> {dest_path}")
        await client.download_media(msg, file=dest_path, progress_callback=progress_fn)

        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            logger.info(f"Direct MTProto download complete: {dest_path} ({os.path.getsize(dest_path)} bytes)")
            return True
        else:
            logger.warning(f"Direct MTProto download finished but file is missing or empty: {dest_path}")
            return False
    except Exception as e:
        logger.error(f"MTProto direct download failed: {e}", exc_info=True)
        return False


async def upload_direct_media(
    chat_id: int,
    file_path: str,
    file_name: str,
    caption: str,
    progress_fn: Optional[Callable] = None
) -> bool:
    """
    Uploads a file up to 2GB directly into Telegram chat via MTProto.
    """
    client = await get_mtproto_client()
    if not client:
        logger.warning("MTProto client not available for direct upload.")
        return False

    if not os.path.exists(file_path):
        logger.warning(f"File to upload does not exist: {file_path}")
        return False

    try:
        logger.info(f"Starting direct MTProto upload: {file_path} ({os.path.getsize(file_path)} bytes)")
        attributes = [DocumentAttributeFilename(file_name)]
        await client.send_file(
            entity=chat_id,
            file=file_path,
            caption=caption,
            parse_mode="markdown",
            attributes=attributes,
            progress_callback=progress_fn
        )
        logger.info(f"Direct MTProto upload complete: {file_path}")
        return True
    except Exception as e:
        logger.error(f"MTProto direct upload failed: {e}", exc_info=True)
        return False
