from pathlib import Path

MAX_CHARS = 2000


def extract_pdf(path: Path) -> dict:
    text = ""
    metadata: dict = {}

    # Try pymupdf first
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(path))
        meta = doc.metadata or {}
        metadata["title"] = meta.get("title", "")
        metadata["author"] = meta.get("author", "")
        for page in doc:
            text += page.get_text()
            if len(text) >= MAX_CHARS:
                break
        doc.close()
        if text.strip():
            return {"summary_text": text[:MAX_CHARS], "metadata": metadata}
    except Exception:
        pass

    # Fallback: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text
                if len(text) >= MAX_CHARS:
                    break
        if text.strip():
            return {"summary_text": text[:MAX_CHARS], "metadata": metadata}
    except Exception:
        pass

    return {"summary_text": "", "metadata": metadata}
