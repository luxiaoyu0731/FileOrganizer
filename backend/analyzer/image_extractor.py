from pathlib import Path


def extract_image(path: Path) -> dict:
    metadata: dict = {}
    ext = path.suffix.lower()

    # HEIC support
    if ext in {".heic", ".heif"}:
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass

    try:
        import piexif
        from PIL import Image

        img = Image.open(str(path))
        metadata["format"] = img.format
        metadata["size"] = f"{img.width}x{img.height}"
        metadata["mode"] = img.mode

        exif_data = img.info.get("exif")
        if exif_data:
            try:
                exif = piexif.load(exif_data)
                exif_ifd = exif.get("Exif", {})
                gps_ifd = exif.get("GPS", {})
                zeroth = exif.get("0th", {})

                dt = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)
                if dt:
                    metadata["date_taken"] = dt.decode("utf-8", errors="replace")

                make = zeroth.get(piexif.ImageIFD.Make)
                model = zeroth.get(piexif.ImageIFD.Model)
                if make:
                    metadata["camera_make"] = make.decode("utf-8", errors="replace").strip()
                if model:
                    metadata["camera_model"] = model.decode("utf-8", errors="replace").strip()

                if gps_ifd:
                    metadata["has_gps"] = True
            except Exception:
                pass
    except Exception as e:
        metadata["extraction_error"] = str(e)

    summary = f"图片 {metadata.get('size', '')} {metadata.get('date_taken', '')} {metadata.get('camera_make', '')} {metadata.get('camera_model', '')}".strip()
    return {"summary_text": summary, "metadata": metadata}
