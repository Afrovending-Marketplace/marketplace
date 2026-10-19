from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS * 2
SIZES = (("main", 1600, 82), ("thumb", 480, 75))


def optimize(data: bytes) -> dict:
    """Validate an uploaded image and return WebP renditions (EXIF stripped)."""
    try:
        Image.open(BytesIO(data)).verify()
        img = Image.open(BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise ValueError("Image is too large (max 40 megapixels).")
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
        raise ValueError("That file isn't a valid image.")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    out = {"width": img.width, "height": img.height}
    for name, size, quality in SIZES:
        copy = img.copy()
        copy.thumbnail((size, size), Image.LANCZOS)
        buf = BytesIO()
        copy.save(buf, "WEBP", quality=quality, method=4)
        out[name] = buf.getvalue()
    return out
