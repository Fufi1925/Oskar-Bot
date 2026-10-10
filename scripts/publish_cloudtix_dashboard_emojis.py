"""Publish all dashboard-enabled emoji packs and their local previews."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "bot/assets/emojis/cloudtix"
PUBLIC = ROOT / "dashboard/public/emojis/cloudtix"


def publish():
    entries = []
    for relative in ("emojis.json", "discord-color/emojis.json",
                     "discord-utility/emojis.json", "bot-gray/emojis.json"):
        path = ASSETS / relative
        if path.exists():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            for entry in manifest["emojis"]:
                if entry.get("dashboard_visible", True):
                    entries.append({**entry, "provider": entry.get("provider", manifest["provider"])})
    PUBLIC.mkdir(parents=True, exist_ok=True)
    # Remove previews that have been retired from the dashboard catalog.
    previous_path = PUBLIC / "emojis.json"
    visible_files = {entry["file"] for entry in entries}
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        for entry in previous.get("emojis", []):
            target = (PUBLIC / entry["file"]).resolve()
            if entry["file"] not in visible_files and target.is_relative_to(PUBLIC.resolve()):
                target.unlink(missing_ok=True)
    for entry in entries:
        target = PUBLIC / entry["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ASSETS / entry["file"], target)
    shutil.copyfile(ASSETS / "LICENSE.lucide.txt", PUBLIC / "LICENSE.lucide.txt")
    providers = list(dict.fromkeys(entry["provider"] for entry in entries))
    catalog = {"schema_version": 1, "brand": "CloudTIX", "provider": ", ".join(providers),
               "license_file": "LICENSE.lucide.txt", "emojis": entries}
    (PUBLIC / "emojis.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Published {len(entries)} dashboard emoji previews.")


if __name__ == "__main__":
    publish()
