"""
scripts/generate_icon.py

Generate DotGhostBoard application icons from the master artwork.

Source:
    data/icons/source/dotghostboard_master.png

Output:
    data/icons/icon_16.png
    data/icons/icon_32.png
    data/icons/icon_48.png
    data/icons/icon_64.png
    data/icons/icon_128.png
    data/icons/icon_256.png
    data/icons/icon_512.png
    data/icons/icon.png
"""

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


BASE_DIR = Path(__file__).resolve().parent.parent

ICONS_DIR = BASE_DIR / "data" / "icons"
SOURCE_DIR = ICONS_DIR / "source"

SOURCE = SOURCE_DIR / "dotghostboard_master.png"

SIZES = [
    16,
    32,
    48,
    64,
    128,
    256,
    512,
]


def prepare_master() -> Image.Image:
    """Load and prepare the high-resolution DotGhostBoard artwork."""

    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Master icon not found:\n{SOURCE}"
        )

    img = Image.open(SOURCE).convert("RGBA")

    # Force square canvas without distortion.
    size = min(img.width, img.height)

    left = (img.width - size) // 2
    top = (img.height - size) // 2

    img = img.crop(
        (
            left,
            top,
            left + size,
            top + size,
        )
    )

    # Keep a large master image for high-quality downsampling.
    img = ImageOps.fit(
        img,
        (1024, 1024),
        method=Image.Resampling.LANCZOS,
    )

    return img


def optimize_small_icon(
    image: Image.Image,
    size: int,
) -> Image.Image:
    """
    Downsample the master image while preserving the neon edges.

    Smaller icons need slightly more contrast/sharpness because
    the glow otherwise makes the logo blurry.
    """

    icon = image.resize(
        (size, size),
        Image.Resampling.LANCZOS,
    )

    if size <= 64:
        icon = ImageEnhance.Contrast(icon).enhance(1.08)
        icon = ImageEnhance.Sharpness(icon).enhance(1.25)

    if size <= 32:
        icon = icon.filter(
            ImageFilter.UnsharpMask(
                radius=0.6,
                percent=130,
                threshold=2,
            )
        )

    return icon


def generate_all():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    master = prepare_master()

    print("Generating DotGhostBoard icons...\n")

    for size in SIZES:
        icon = optimize_small_icon(master, size)

        output = ICONS_DIR / f"icon_{size}.png"

        icon.save(
            output,
            "PNG",
            optimize=True,
        )

        print(
            f"  ✓ {output.name:<14} "
            f"{size}x{size}"
        )

    # Main application icon
    main_icon = optimize_small_icon(master, 256)

    output = ICONS_DIR / "icon.png"

    main_icon.save(
        output,
        "PNG",
        optimize=True,
    )

    print("  ✓ icon.png       256x256 — main")

    print(
        f"\n👻 All icons saved to:\n"
        f"   {ICONS_DIR}"
    )


if __name__ == "__main__":
    generate_all()
