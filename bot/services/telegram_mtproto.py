import os
import inspect
import asyncio
import logging
from typing import Optional, Callable
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.tl.types import DocumentAttributeFilename
from config import BOT_TOKEN
from bot.services.fast_telethon import fast_upload_file

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
            logger.info("📡 Connecting High-Speed Telethon MTProto client (2GB direct support)...")
            client = TelegramClient(MemorySession(), API_ID, API_HASH)
            await client.start(bot_token=BOT_TOKEN)
            if client.is_connected():
                _mtproto_client = client
                logger.info("✅ High-Speed Telethon MTProto client connected!")
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
    Downloads any media up to 2GB directly from Telegram using 512KB high-speed chunks.
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

        doc = getattr(msg, "document", None) or getattr(msg, "media", None)
        total_size = getattr(doc, "size", 0)

        # High-speed chunk download (512KB chunks)
        downloaded = 0
        with open(dest_path, "wb") as f:
            async for chunk in client.iter_download(msg.media, request_size=512 * 1024, chunk_size=512 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_fn:
                    res = progress_fn(downloaded, total_size)
                    if inspect.isawaitable(res):
                        await res

        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            logger.info(f"High-speed download complete: {dest_path} ({os.path.getsize(dest_path)} bytes)")
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"High-speed iter_download error: {e}. Falling back to standard download_media...")
        try:
            await client.download_media(msg, file=dest_path, progress_callback=progress_fn)
            return os.path.exists(dest_path) and os.path.getsize(dest_path) > 0
        except Exception as fallback_e:
            logger.error(f"Fallback download also failed: {fallback_e}")
            return False


async def upload_direct_media(
    chat_id: int,
    file_path: str,
    file_name: str,
    caption: str,
    progress_fn: Optional[Callable] = None
) -> bool:
    """
    Uploads file up to 2GB using high-speed parallel 512KB chunks.
    """
    client = await get_mtproto_client()
    if not client:
        logger.warning("MTProto client not available for direct upload.")
        return False

    if not os.path.exists(file_path):
        logger.warning(f"File to upload does not exist: {file_path}")
        return False

    try:
        logger.info(f"Starting High-Speed parallel upload: {file_path} ({os.path.getsize(file_path)} bytes)")
        
        # Parallel chunk upload (512KB parts)
        input_file = await fast_upload_file(client, file_path, progress_callback=progress_fn)
        
        attributes = [DocumentAttributeFilename(file_name)]
        await client.send_file(
            entity=chat_id,
            file=input_file,
            caption=caption,
            parse_mode="markdown",
            attributes=attributes
        )
        logger.info(f"Direct high-speed upload complete: {file_path}")
        return True
    except Exception as e:
        logger.error(f"High-speed parallel upload failed: {e}. Falling back to standard send_file...", exc_info=True)
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
