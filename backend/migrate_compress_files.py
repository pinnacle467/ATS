"""One-off migration: retroactively compress already-stored resume files."""
import asyncio
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from database import db  # noqa: E402
from resume_compressor import compress_resume  # noqa: E402


async def main():
    total_before = 0
    total_after = 0
    n = 0
    cursor = db.files.find({})
    async for doc in cursor:
        filename = doc.get('filename', '')
        ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
        if ext not in ('pdf', 'docx'):
            continue
        raw = base64.b64decode(doc['data_b64'])
        before = len(raw)
        compressed = compress_resume(raw, filename)
        after = len(compressed)
        total_before += before
        total_after += after
        n += 1
        if after < before:
            await db.files.update_one({'id': doc['id']}, {'$set': {
                'data_b64': base64.b64encode(compressed).decode(),
                'size': after,
            }})
        print(f"{filename}: {before} -> {after} bytes ({round((1-after/before)*100,1) if before else 0}% reduction)")
    print(f"\nTOTAL: {n} files, {total_before} -> {total_after} bytes, saved {total_before - total_after} bytes ({round((1-total_after/total_before)*100,1) if total_before else 0}%)")


asyncio.run(main())
