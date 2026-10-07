import re
from pathlib import Path


def _clean_name(name: str) -> str:
    """Remove illegal characters, collapse whitespace, truncate to 80 chars."""
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    if name in {".", ".."}:
        raise ValueError("Invalid path segment")
    return name[:80]


def _extract_date(classification: dict, file_path: str) -> str:
    """Return YYYY-MM-DD from various sources."""
    # 1. From AI metadata date fields
    meta = classification.get("metadata", {})
    for key in ("date_taken", "created_date", "modified_date"):
        val = meta.get(key, "")
        if isinstance(val, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", val[:10]):
            return val[:10]
    # 2. From modified_time on the scan result (passed via classification)
    modified_time = classification.get("modified_time", "")
    if isinstance(modified_time, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", modified_time[:10]):
        return modified_time[:10]
    # 3. Fallback: today
    from datetime import date
    return date.today().isoformat()


def build_destination(
    classification: dict,
    archive_root: str,
    rename_strategy: str,
) -> Path:
    """Return the full destination path for a classified file."""
    src = Path(classification["path"])
    ext = src.suffix
    cat = _clean_name(classification.get("category", "其他"))
    subcat = _clean_name(classification.get("subcategory", ""))
    suggested = _clean_name(classification.get("suggested_name", src.stem))
    date_str = _extract_date(classification, str(src))

    if rename_strategy == "semantic_date":
        new_name = f"{date_str}_{suggested}{ext}"
    elif rename_strategy == "date_prefix":
        new_name = f"{date_str}_{src.stem}{ext}"
    else:  # preserve_original
        new_name = src.name

    # Multi-level path support: sub_path takes precedence over category/subcategory
    sub_path = classification.get("sub_path", [])
    if sub_path:
        dest_dir = Path(archive_root)
        for segment in sub_path:
            dest_dir = dest_dir / _clean_name(segment)
    else:
        dest_dir = Path(archive_root) / cat
        if subcat:
            dest_dir = dest_dir / subcat
    root = Path(archive_root).resolve()
    destination = dest_dir / new_name
    if not destination.resolve().is_relative_to(root):
        raise ValueError("Destination escapes archive root")
    return destination
