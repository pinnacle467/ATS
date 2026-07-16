"""Auto-compress uploaded resumes (PDF/DOCX) to reduce storage footprint.

All operations are lossless with respect to visible content/quality:
- PDF: PyMuPDF font-subsetting + structural garbage collection + stream deflation.
  This never touches rendered text or images pixel-for-pixel — it only removes
  duplicate/unused objects and re-encodes streams more efficiently.
- DOCX: DOCX is a ZIP archive; we simply re-zip every internal part with the
  maximum DEFLATE compression level. Content is byte-identical once unzipped.

Compression always falls back to the original bytes on any error, or if the
"compressed" result is not actually smaller (so we never risk corrupting a
file or making it bigger).
"""
import io
import logging
import zipfile

logger = logging.getLogger(__name__)


def _compress_pdf(data: bytes) -> bytes:
    import fitz  # pymupdf

    doc = fitz.open(stream=data, filetype='pdf')
    try:
        try:
            doc.subset_fonts()
        except Exception:
            pass  # font subsetting is a bonus, not required
        out = doc.tobytes(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True)
    finally:
        doc.close()
    return out


def _compress_docx(data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data), 'r') as zin:
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            for item in zin.infolist():
                zout.writestr(item.filename, zin.read(item.filename), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return buf.getvalue()


def compress_resume(data: bytes, filename: str) -> bytes:
    """Compress a resume file to its smallest safe size. Always returns valid
    bytes for the same format — falls back to the original on any issue."""
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
    try:
        if ext == 'pdf':
            compressed = _compress_pdf(data)
        elif ext == 'docx':
            compressed = _compress_docx(data)
        else:
            return data
    except Exception as e:
        logger.warning(f'Resume compression failed for {filename}, storing original: {e}')
        return data

    if not compressed or len(compressed) >= len(data):
        return data
    return compressed
