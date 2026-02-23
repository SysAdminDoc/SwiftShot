"""
SwiftShot Icon Generator
Converts swiftshot.png into a proper multi-size swiftshot.ico.

Run:  python generate_icon.py
In:   swiftshot.png  (must be in same directory)
Out:  swiftshot.ico  (9 sizes: 16-256px)

Requires: Pillow
"""

import os
import sys
import struct
import io


def generate_ico(png_path, ico_path):
    """Convert a PNG to a multi-size ICO with manually built binary format."""
    from PIL import Image

    if not os.path.isfile(png_path):
        print(f"  ERROR: {png_path} not found.")
        sys.exit(1)

    img = Image.open(png_path).convert("RGBA")
    print(f"  Source: {img.size[0]}x{img.size[1]}")

    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    count = len(sizes)

    # ICO header
    header = struct.pack("<HHH", 0, 1, count)

    # Build directory entries and image data
    data_offset = 6 + count * 16
    entries = []
    image_data_list = []

    for sz in sizes:
        resized = img.resize((sz, sz), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        w = 0 if sz == 256 else sz
        h = 0 if sz == 256 else sz

        entry = struct.pack("<BBBBHHII",
            w, h, 0, 0, 1, 32,
            len(png_bytes), data_offset
        )
        entries.append(entry)
        image_data_list.append(png_bytes)
        data_offset += len(png_bytes)
        print(f"  Generated {sz}x{sz} ({len(png_bytes):,} bytes)")

    with open(ico_path, "wb") as f:
        f.write(header)
        for entry in entries:
            f.write(entry)
        for png_data in image_data_list:
            f.write(png_data)

    file_size = os.path.getsize(ico_path)
    print(f"\n  ICO saved: {ico_path} ({file_size:,} bytes, {count} sizes)")


if __name__ == "__main__":
    try:
        from PIL import Image
    except ImportError:
        print("Installing Pillow...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])

    print("\nSwiftShot Icon Generator")
    print("=" * 40)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(script_dir, "swiftshot.png")
    ico_path = os.path.join(script_dir, "swiftshot.ico")

    generate_ico(png_path, ico_path)
    print("\nDone!")
