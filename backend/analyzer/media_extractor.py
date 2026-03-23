from pathlib import Path


def extract_media(path: Path) -> dict:
    metadata: dict = {}
    try:
        import mutagen
        f = mutagen.File(str(path), easy=True)
        if f is not None:
            tags = dict(f.tags or {})
            metadata["title"] = str(tags.get("title", [""])[0]) if tags.get("title") else ""
            metadata["artist"] = str(tags.get("artist", [""])[0]) if tags.get("artist") else ""
            metadata["album"] = str(tags.get("album", [""])[0]) if tags.get("album") else ""
            if hasattr(f, "info") and hasattr(f.info, "length"):
                metadata["duration_s"] = round(f.info.length, 1)
        summary_parts = [v for v in [metadata.get("title"), metadata.get("artist"), metadata.get("album")] if v]
        return {"summary_text": " / ".join(summary_parts), "metadata": metadata}
    except Exception as e:
        return {"summary_text": "", "metadata": {"extraction_error": str(e)}}
