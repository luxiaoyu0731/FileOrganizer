from pathlib import Path

# Extension → (category, subcategory)
EXT_MAP: dict[str, tuple[str, str]] = {
    # Documents
    ".pdf": ("文档", "PDF"),
    ".doc": ("文档", "Word文档"),
    ".docx": ("文档", "Word文档"),
    ".xls": ("文档", "表格"),
    ".xlsx": ("文档", "表格"),
    ".csv": ("文档", "表格"),
    ".ppt": ("文档", "演示文稿"),
    ".pptx": ("文档", "演示文稿"),
    ".txt": ("文档", "文本"),
    ".md": ("文档", "Markdown"),
    ".epub": ("文档", "电子书"),
    # Images
    ".jpg": ("图片", "照片"),
    ".jpeg": ("图片", "照片"),
    ".png": ("图片", "图片"),
    ".gif": ("图片", "动图"),
    ".bmp": ("图片", "图片"),
    ".webp": ("图片", "图片"),
    ".heic": ("图片", "照片"),
    ".heif": ("图片", "照片"),
    ".tiff": ("图片", "图片"),
    ".svg": ("图片", "矢量图"),
    # Video
    ".mp4": ("视频", "视频"),
    ".mov": ("视频", "视频"),
    ".avi": ("视频", "视频"),
    ".mkv": ("视频", "视频"),
    ".wmv": ("视频", "视频"),
    ".flv": ("视频", "视频"),
    ".m4v": ("视频", "视频"),
    # Audio
    ".mp3": ("音频", "音乐"),
    ".flac": ("音频", "音乐"),
    ".aac": ("音频", "音频"),
    ".wav": ("音频", "音频"),
    ".ogg": ("音频", "音频"),
    ".m4a": ("音频", "音乐"),
    # Code
    ".py": ("代码", "Python"),
    ".js": ("代码", "JavaScript"),
    ".ts": ("代码", "TypeScript"),
    ".tsx": ("代码", "TypeScript"),
    ".jsx": ("代码", "JavaScript"),
    ".java": ("代码", "Java"),
    ".go": ("代码", "Go"),
    ".rs": ("代码", "Rust"),
    ".c": ("代码", "C"),
    ".cpp": ("代码", "C++"),
    ".sh": ("代码", "脚本"),
    # Archives
    ".zip": ("压缩包", "ZIP"),
    ".rar": ("压缩包", "RAR"),
    ".7z": ("压缩包", "7Z"),
    ".tar": ("压缩包", "TAR"),
    ".gz": ("压缩包", "GZ"),
}


def classify_by_extension(file_path: str, suggested_name: str = "") -> dict:
    ext = Path(file_path).suffix.lower()
    category, subcategory = EXT_MAP.get(ext, ("其他", "其他"))
    name = suggested_name or Path(file_path).stem
    return {
        "path": file_path,
        "category": category,
        "subcategory": subcategory,
        "suggested_name": name,
        "confidence": 0.5,
        "reasoning": f"根据文件扩展名 {ext} 自动分类",
        "classification_method": "fallback_extension",
    }
