import asyncio
import hashlib
import inspect
import logging
import math
import os
from typing import Optional, List, Union, Tuple, BinaryIO
from telethon import utils, helpers, TelegramClient
from telethon.crypto import AuthKey
from telethon.network import MTProtoSender
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import GetFileRequest, SaveFilePartRequest, SaveBigFilePartRequest
from telethon.tl.types import (
    Document,
    InputFileLocation,
    InputDocumentFileLocation,
    InputPhotoFileLocation,
    InputPeerPhotoFileLocation,
    TypeInputFile,
    InputFileBig,
    InputFile
)

log = logging.getLogger("fast_telethon")

TypeLocation = Union[Document, InputDocumentFileLocation, InputPeerPhotoFileLocation, InputFileLocation, InputPhotoFileLocation]


class DownloadSender:
    def __init__(self, client: TelegramClient, sender: MTProtoSender, file_loc: TypeLocation, offset: int, limit: int, stride: int, count: int) -> None:
        self.sender = sender
        self.client = client
        self.request = GetFileRequest(file_loc, offset=offset, limit=limit)
        self.stride = stride
        self.remaining = count

    async def next(self) -> Optional[Tuple[int, bytes]]:
        if not self.remaining:
            return None
        current_offset = self.request.offset
        result = await self.client._call(self.sender, self.request)
        self.remaining -= 1
        self.request.offset += self.stride
        return current_offset, result.bytes

    async def disconnect(self) -> None:
        await self.sender.disconnect()


class UploadSender:
    def __init__(self, client: TelegramClient, sender: MTProtoSender, file_id: int, part_count: int, big: bool, index: int, stride: int, loop: asyncio.AbstractEventLoop) -> None:
        self.client = client
        self.sender = sender
        self.part_count = part_count
        if big:
            self.request = SaveBigFilePartRequest(file_id, index, part_count, b"")
        else:
            self.request = SaveFilePartRequest(file_id, index, b"")
        self.stride = stride
        self.previous = None
        self.loop = loop

    async def next(self, data: bytes) -> None:
        if self.previous:
            await self.previous
        self.previous = self.loop.create_task(self._next(data))

    async def _next(self, data: bytes) -> None:
        self.request.bytes = data
        await self.client._call(self.sender, self.request)
        self.request.file_part += self.stride

    async def disconnect(self) -> None:
        if self.previous:
            await self.previous
        await self.sender.disconnect()


class ParallelTransferrer:
    def __init__(self, client: TelegramClient, dc_id: Optional[int] = None) -> None:
        self.client = client
        self.loop = self.client.loop
        self.dc_id = dc_id or self.client.session.dc_id
        self.auth_key = (
            None if dc_id and self.client.session.dc_id != dc_id
            else self.client.session.auth_key
        )
        self.senders: Optional[List[MTProtoSender]] = None

    async def _init_senders(self, count: int, file_loc: TypeLocation = None) -> None:
        if self.senders:
            return

        if not self.auth_key:
            np = await self.client(ExportAuthorizationRequest(self.dc_id))
            self.auth_key = AuthKey(np.bytes)
            client = TelegramClient(None, self.client.api_id, self.client.api_hash, loop=self.loop)
            await client.connect()
            try:
                await client(ImportAuthorizationRequest(np.id, np.bytes))
            except Exception:
                await client.disconnect()
                raise
        else:
            client = self.client

        connects = [client._connect() for _ in range(count)]
        connects = await asyncio.gather(*connects, return_exceptions=True)
        self.senders = []
        for conn in connects:
            if isinstance(conn, BaseException):
                continue
            sender = MTProtoSender(self.auth_key, log=log)
            sender._dc_id = self.dc_id
            try:
                await sender.connect(conn)
                self.senders.append(sender)
            except Exception:
                pass

        if not self.senders:
            raise ConnectionError("Failed to create parallel connections")

        if self.client._init_conn:
            try:
                await self.client._init_conn(self.senders[0])
            except Exception:
                pass

        req = InvokeWithLayerRequest(LAYER, ExportAuthorizationRequest(self.dc_id))
        if len(self.senders) > 1:
            await asyncio.gather(*(sender.send(req) for sender in self.senders[1:]), return_exceptions=True)
        await self.senders[0].send(req)
        for sender in self.senders:
            try:
                sender.get_response(req)
            except Exception:
                pass

    async def upload(self, file: BinaryIO, total_size: int, progress_callback=None) -> Tuple[TypeInputFile, int]:
        part_size = 512 * 1024
        big = total_size > 10 * 1024 * 1024
        part_count = math.ceil(total_size / part_size)
        connection_count = min(max(4, math.ceil(total_size / (512 * 1024 * 4))), 10)

        await self._init_senders(connection_count)
        connections = len(self.senders)
        file_id = helpers.generate_random_long()

        senders = [
            UploadSender(
                self.client, self.senders[i], file_id, part_count,
                big, index=i, stride=connections, loop=self.loop
            )
            for i in range(connections)
        ]

        hash_md5 = hashlib.md5()
        uploaded_bytes = 0

        queue = asyncio.Queue(connections * 4)

        async def sender_worker(sender: UploadSender):
            while True:
                item = await queue.get()
                if item is None:
                    queue.task_done()
                    break
                idx, data = item
                if not big:
                    hash_md5.update(data)
                await sender.next(data)
                queue.task_done()

        workers = [asyncio.create_task(sender_worker(sender)) for sender in senders]

        part_index = 0
        while True:
            data = file.read(part_size)
            if not data:
                break
            await queue.put((part_index, data))
            uploaded_bytes += len(data)
            if progress_callback:
                r = progress_callback(uploaded_bytes, total_size)
                if inspect.isawaitable(r):
                    await r
            part_index += 1

        for _ in workers:
            await queue.put(None)

        await queue.join()
        await asyncio.gather(*(w for w in workers))
        await asyncio.gather(*(sender.disconnect() for sender in senders))

        if big:
            return InputFileBig(file_id, part_count, "upload.ipa"), total_size
        else:
            return InputFile(file_id, part_count, "upload.ipa", hash_md5.hexdigest()), total_size

    async def download_to_file(self, file_loc: TypeLocation, total_size: int, dest_path: str, progress_callback=None) -> bool:
        part_size = 512 * 1024
        part_count = math.ceil(total_size / part_size)
        connection_count = min(max(4, math.ceil(total_size / (512 * 1024 * 4))), 8)

        await self._init_senders(connection_count, file_loc)
        connections = len(self.senders)
        minimum, remainder = divmod(part_count, connections)

        senders = []
        offset = 0
        for i in range(connections):
            count = minimum + (1 if i < remainder else 0)
            if count == 0:
                continue
            senders.append(DownloadSender(
                self.client, self.senders[i], file_loc,
                offset=offset,
                limit=part_size,
                stride=part_size * connections,
                count=count
            ))
            offset += part_size

        # Pre-allocate output file
        with open(dest_path, "wb") as f:
            f.truncate(total_size)

        downloaded_bytes = 0
        lock = asyncio.Lock()

        async def worker(sender: DownloadSender):
            nonlocal downloaded_bytes
            with open(dest_path, "r+b") as fp:
                while True:
                    res = await sender.next()
                    if not res:
                        break
                    chunk_offset, data = res
                    fp.seek(chunk_offset)
                    fp.write(data)
                    async with lock:
                        downloaded_bytes += len(data)
                        if progress_callback:
                            r = progress_callback(downloaded_bytes, total_size)
                            if inspect.isawaitable(r):
                                await r

        await asyncio.gather(*(worker(s) for s in senders))
        await asyncio.gather(*(s.disconnect() for s in senders))
        return os.path.exists(dest_path) and os.path.getsize(dest_path) == total_size


async def fast_upload_file(
    client: TelegramClient,
    file_path: str,
    progress_callback=None
) -> TypeInputFile:
    """Uploads file using parallel MTProto connections (512KB parts)."""
    file_size = os.path.getsize(file_path)
    try:
        with open(file_path, "rb") as f:
            uploader = ParallelTransferrer(client)
            res, _ = await uploader.upload(f, file_size, progress_callback=progress_callback)
            return res
    except Exception as e:
        log.warning(f"Parallel upload fallback to 512KB single-stream: {e}")
        return await client.upload_file(
            file_path,
            part_size_kb=512,
            progress_callback=progress_callback
        )


async def fast_download_media(
    client: TelegramClient,
    message,
    dest_path: str,
    progress_callback=None
) -> bool:
    """Downloads media from message using parallel MTProto connections (512KB parts)."""
    try:
        doc = getattr(message, "document", None) or getattr(message, "media", None)
        total_size = getattr(doc, "size", 0)
        if not doc or total_size == 0:
            return False

        dc_id, location = utils.get_input_location(doc)
        downloader = ParallelTransferrer(client, dc_id)
        success = await downloader.download_to_file(location, total_size, dest_path, progress_callback)
        if success:
            return True
    except Exception as e:
        log.warning(f"Parallel download fallback to iter_download: {e}")

    # Fallback to high-speed 512KB iter_download
    try:
        total_size = getattr(getattr(message, "document", None), "size", 0)
        downloaded = 0
        with open(dest_path, "wb") as f:
            async for chunk in client.iter_download(message.media, request_size=512 * 1024, chunk_size=512 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    r = progress_callback(downloaded, total_size)
                    if inspect.isawaitable(r):
                        await r
        return os.path.exists(dest_path) and os.path.getsize(dest_path) > 0
    except Exception as fallback_e:
        log.error(f"Iter_download fallback failed: {fallback_e}")
        return False
