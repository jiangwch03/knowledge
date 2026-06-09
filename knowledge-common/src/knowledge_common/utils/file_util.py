from pathlib import Path

import aiofiles


class FileUtil:
    @staticmethod
    async def file_chunk_stream(file_path: Path, chunk_size: int = 256 * 1024):
        """异步流式读取文件，内存中仅保留一个 chunk 大小的缓冲区"""
        async with aiofiles.open(file_path, 'rb') as f:
            while chunk := await f.read(chunk_size):
                yield chunk