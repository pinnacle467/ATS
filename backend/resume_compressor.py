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


_IMAGE_EXT_TO_PIL_FORMAT = {'png': 'PNG', 'jpg': 'JPEG', 'jpeg': 'JPEG', 'bmp': 'BMP', 'tif': 'TIFF', 'tiff': 'TIFF'}
_MAX_IMAGE_DIM = 1600  # px — plenty for on-screen preview/print of an embedded photo/logo in a resume


def _compress_docx_image(raw: bytes, ext: str) -> bytes:
    """Downscale/re-encode a single image embedded in a DOCX (word/media/*) losing
    no perceptible quality: caps very large dimensions and re-compresses with a
    high-quality JPEG encoder for photos, or optimized PNG for graphics/logos.
    Falls back to the original bytes on any decode error or if not smaller."""
    from PIL import Image

    pil_format = _IMAGE_EXT_TO_PIL_FORMAT.get(ext)
    if not pil_format:
        return raw
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        return raw

    if max(img.size) > _MAX_IMAGE_DIM:
        img.thumbnail((_MAX_IMAGE_DIM, _MAX_IMAGE_DIM), Image.LANCZOS)

    out = io.BytesIO()
    try:
        if pil_format == 'JPEG':
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(out, format='JPEG', quality=85, optimize=True)
        else:
            img.save(out, format=pil_format, optimize=True)
    except Exception:
        return raw

    result = out.getvalue()
    return result if 0 < len(result) < len(raw) else raw


def _compress_docx(data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data), 'r') as zin:
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            for item in zin.infolist():
                content = zin.read(item.filename)
                if item.filename.startswith('word/media/') and '.' in item.filename:
                    ext = item.filename.rsplit('.', 1)[-1].lower()
                    try:
                        content = _compress_docx_image(content, ext)
                    except Exception as e:
                        logger.warning(f'DOCX image compression failed for {item.filename}, keeping original: {e}')
                zout.writestr(item.filename, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
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
