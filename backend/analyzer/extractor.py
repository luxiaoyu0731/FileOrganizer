from pathlib import Path
from typing import Optional

PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".heif"}
WORD_EXTS = {".docx", ".doc"}
EXCEL_EXTS = {".xlsx", ".xls", ".csv"}
PPT_EXTS = {".pptx", ".ppt"}
AUDIO_EXTS = {".mp3", ".flac", ".aac", ".ogg", ".wav", ".m4a", ".wma"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v"}
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".go", ".rs", ".rb", ".php", ".sh"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}


def extract(file_path: Path) -> dict:
    ext = file_path.suffix.lower()
    try:
        if ext in PDF_EXTS:
            from analyzer.pdf_extractor import extract_pdf
            return extract_pdf(file_path)
        if ext in IMAGE_EXTS:
            from analyzer.image_extractor import extract_image
            return extract_image(file_path)
        if ext in WORD_EXTS:
            from analyzer.office_extractor import extract_docx
            return extract_docx(file_path)
        if ext in EXCEL_EXTS:
            from analyzer.office_extractor import extract_xlsx
            return extract_xlsx(file_path)
        if ext in PPT_EXTS:
            from analyzer.office_extractor import extract_pptx
            return extract_pptx(file_path)
        if ext in AUDIO_EXTS or ext in VIDEO_EXTS:
            from analyzer.media_extractor import extract_media
            return extract_media(file_path)
        if ext in CODE_EXTS:
            return _extract_code(file_path)
        if ext in ARCHIVE_EXTS:
            return _extract_archive(file_path)
    except Exception as e:
        return {"summary_text": "", "metadata": {"extraction_error": str(e)}}
    return {"summary_text": "", "metadata": {}}


def _extract_code(path: Path) -> dict:
    try:
        lines = path.read_text(errors="replace").splitlines()[:50]
        return {"summary_text": "\n".join(lines), "metadata": {"type": "code"}}
    except Exception:
        return {"summary_text": "", "metadata": {}}


def _extract_archive(path: Path) -> dict:
    try:
        import zipfile
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()[:30]
            return {"summary_text": "\n".join(names), "metadata": {"type": "archive", "file_count": len(names)}}
    except Exception:
        pass
    return {"summary_text": "", "metadata": {"type": "archive"}}
