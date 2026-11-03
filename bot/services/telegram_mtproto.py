import os
import inspect
import asyncio
import logging
from typing import Optional, Callable
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.tl.types import DocumentAttributeFilename
from config import BOT_TOKEN
from bot.services.fast_telethon import fast_upload_file, fast_download_media

logger = logging.getLogger(__name__)

# Official public Telegram API credentials
DEFAULT_API_ID = 2040
DEFAULT_API_HASH = "b18441a1ff607e10a989891a5462e627"

API_ID = int(os.getenv("TELEGRAM_API_ID", str(DEFAULT_API_ID)))
API_HASH = os.getenv("TELEGRAM_API_HASH", DEFAULT_API_HASH)

_mtproto_client: Optional[TelegramClient] = None
_client_lock = asyncio.Lock()


async def get_mtproto_client() -> Optional[TelegramClient]:
    """Returns singleton Telethon MTProto client, initializing if needed."""
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
            logger.info("📡 Connecting Ultra-Speed Telethon MTProto client...")
            client = TelegramClient(MemorySession(), API_ID, API_HASH)
            await client.start(bot_token=BOT_TOKEN)
            if client.is_connected():
                _mtproto_client = client
                logger.info("✅ Ultra-Speed Telethon MTProto client connected!")
                return _mtproto_client
        except Exception as e:
            logger.error(f"❌ Failed to start Telethon MTProto client: {e}")
            return None

    return None


async def stop_mtproto_client():
    """Disconnects MTProto client gracefully."""
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
    Downloads any media up to 2GB directly from Telegram using multi-connection parallel 512KB chunks.
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

        return await fast_download_media(client, msg, dest_path, progress_callback=progress_fn)
    except Exception as e:
        logger.error(f"download_direct_media error: {e}")
        return False


async def upload_direct_media(
    chat_id: int,
    file_path: str,
    file_name: str,
    caption: str,
    progress_fn: Optional[Callable] = None
) -> bool:
    """
    Uploads file up to 2GB using ultra-fast parallel 512KB chunks.
    """
    client = await get_mtproto_client()
    if not client:
        logger.warning("MTProto client not available for direct upload.")
        return False

    if not os.path.exists(file_path):
        logger.warning(f"File to upload does not exist: {file_path}")
        return False

    try:
        logger.info(f"Starting ultra-speed parallel upload: {file_path}")
        input_file = await fast_upload_file(client, file_path, progress_callback=progress_fn)
        
        attributes = [DocumentAttributeFilename(file_name)]
        await client.send_file(
            entity=chat_id,
            file=input_file,
            caption=caption,
            parse_mode="markdown",
            attributes=attributes
        )
        logger.info(f"Direct upload complete: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Parallel upload failed: {e}. Fallback to standard...", exc_info=True)
        try:
            attributes = [DocumentAttributeFilename(file_name)]
            await client.send_file(
                entity=chat_id,
                file=file_path,
                caption=caption,
                parse_mode="markdown",
                attributes=attributes,
                progress_callback=progress_fn
            )
            return True
        except Exception as fallback_e:
            logger.error(f"Fallback send_file also failed: {fallback_e}")
            return False
