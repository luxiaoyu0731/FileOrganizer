# App Icons

Place the following icon files in this directory before building:

| File | Format | Size | Used by |
|------|--------|------|---------|
| `icon.icns` | Apple ICNS | Multi-resolution (16–1024 px) | macOS .app + DMG |
| `icon.ico` | Windows ICO | Multi-resolution (16–256 px) | Windows installer + taskbar |
| `icon.png` | PNG | 512×512 px minimum | Linux AppImage + system tray fallback |

## Generating icons from a source PNG

With a 1024×1024 PNG source file (`icon-source.png`):

### macOS (requires Xcode command line tools)

```bash
mkdir icon.iconset
for size in 16 32 64 128 256 512; do
  sips -z $size $size icon-source.png --out icon.iconset/icon_${size}x${size}.png
  sips -z $((size*2)) $((size*2)) icon-source.png --out icon.iconset/icon_${size}x${size}@2x.png
done
iconutil -c icns icon.iconset -o icon.icns
rm -rf icon.iconset
```

### Windows ICO (requires ImageMagick)

```bash
magick icon-source.png -resize 256x256 \
  \( -clone 0 -resize 16x16 \) \
  \( -clone 0 -resize 32x32 \) \
  \( -clone 0 -resize 48x48 \) \
  \( -clone 0 -resize 64x64 \) \
  \( -clone 0 -resize 128x128 \) \
  -delete 0 icon.ico
```

### Linux PNG

```bash
sips -z 512 512 icon-source.png --out icon.png
```

## Placeholder for development

electron-builder will skip icons that don't exist during development builds.
For packaged builds, all three files must be present.
