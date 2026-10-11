"""Package imagegen-edited sprite sheets into individual Discord files.

All artwork/color/background edits are in the committed source sheets.
ImageMagick only extracts complete tiles and exports their 128px thumbnails.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image

from publish_cloudtix_dashboard_emojis import publish

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "bot/assets/emojis/cloudtix/neutral"


def tile_bounds(path, expected):
    with Image.open(path) as image:
        width, height = image.size
    result = subprocess.run([
        "convert", str(path), "-alpha", "extract", "-threshold", "20%",
        "-define", "connected-components:verbose=true", "-connected-components", "4", "null:",
    ], check=True, capture_output=True, text=True)
    bounds = {}
    for line in result.stdout.splitlines():
        match = re.search(r"\d+: (\d+)x(\d+)\+(\d+)\+(\d+) ([\d.]+),([\d.]+) (\d+) srgb\(255,255,255\)", line)
        if not match:
            continue
        w, h, x, y = map(int, match.group(1, 2, 3, 4))
        cx, cy = map(float, match.group(5, 6))
        area = int(match.group(7))
        if area < width * height / 16 * 0.15:
            continue
        slot = min(3, int(cy / (height / 4))) * 4 + min(3, int(cx / (width / 4)))
        if slot in bounds:
            raise ValueError(f"Two tiles in sprite slot {slot}: {path.name}")
        # Include antialiased edges outside the segmentation threshold.
        x0, y0 = max(0, x - 3), max(0, y - 3)
        bounds[slot] = (min(width, x + w + 3) - x0,
                        min(height, y + h + 3) - y0, x0, y0)
    if set(bounds) != set(expected):
        raise ValueError(f"Sprite slots do not match design: {path.name}: {sorted(bounds)}")
    return bounds


def main():
    design = json.loads((PACK / "design.json").read_text(encoding="utf-8"))
    entries = []
    for batch in sorted({entry["batch"] for entry in design["entries"]}):
        definitions = [entry for entry in design["entries"] if entry["batch"] == batch]
        sheet = PACK / f"sheets/{batch}.png"
        bounds = tile_bounds(sheet, [entry["slot"] for entry in definitions])
        for definition in definitions:
            key = f"neutral_{definition['key']}"
            filename = key + ".png"
            target = PACK / filename
            w, h, x, y = bounds[definition["slot"]]
            subprocess.run([
                "convert", str(sheet), "-crop", f"{w}x{h}+{x}+{y}", "+repage",
                "-resize", "120x120", "-background", "none", "-gravity", "center",
                "-extent", "128x128", "-strip", str(target),
            ], check=True)
            data = target.read_bytes()
            with Image.open(target) as image:
                if image.size != (128, 128) or image.getchannel("A").getextrema() != (0, 255):
                    raise ValueError(f"Invalid Discord tile: {filename}")
            if len(data) > 256 * 1024:
                raise ValueError(f"Discord file size exceeded: {filename}")
            sha = hashlib.sha256(data).hexdigest()
            entry = {k: v for k, v in definition.items() if k not in ("batch", "slot", "key")}
            entry.update({"key": key, "name": f"ct_{key[:22]}_{sha[:6]}",
                          "file": f"neutral/{filename}", "animated": False,
                          "width": 128, "height": 128, "bytes": len(data), "sha256": sha,
                          "provider": "CloudTIX Neutral", "style": "gray", "background": "gray",
                          "visual_style": "neutral-background", "dashboard_visible": True})
            entries.append(entry)
    if len({entry["key"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate emoji key")
    if len({entry["sha256"] for entry in entries}) != len(entries):
        raise ValueError("Identical output emojis")
    manifest = {"schema_version": 1, "brand": "CloudTIX", "provider": "CloudTIX Neutral",
                "source": "User-uploaded emoji.gg packs, edited with imagegen",
                "emojis": entries}
    (PACK / "emojis.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    publish()
    print(f"Exported {len(entries)} unique neutral Discord emojis; maximum file size {max(e['bytes'] for e in entries)} bytes.")


if __name__ == "__main__":
    main()
