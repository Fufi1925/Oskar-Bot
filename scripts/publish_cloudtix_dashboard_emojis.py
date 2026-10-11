"""Publish all dashboard-enabled emoji packs and their local previews."""
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "bot/assets/emojis/cloudtix"
PUBLIC = ROOT / "dashboard/public/emojis/cloudtix"


def publish():
    entries = []
    retirement_path = ASSETS / "retirement.json"
    retirement = json.loads(retirement_path.read_text(encoding="utf-8")) if retirement_path.exists() else {}
    retired_keys = set(retirement.get("retired_keys", []))
    retired_names = set(retirement.get("names", []))
    neutral_pack = ASSETS / "neutral/emojis.json"
    for relative in ("emojis.json", "discord-color/emojis.json",
                     "discord-utility/emojis.json", "bot-gray/emojis.json", "bot-color/emojis.json", "neutral/emojis.json"):
        path = ASSETS / relative
        if path.exists():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            for entry in manifest["emojis"]:
                visible = entry["file"].startswith("neutral/") if neutral_pack.exists() else entry.get("dashboard_visible", True)
                if visible:
                    entries.append({**entry, "provider": entry.get("provider", manifest["provider"]),
                                    "retired": entry["key"] in retired_keys or entry["name"] in retired_names})
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
    license_files = ["LICENSE.lucide.txt"]
    if (ASSETS / "LICENSE.fontawesome.txt").exists():
        shutil.copyfile(ASSETS / "LICENSE.fontawesome.txt", PUBLIC / "LICENSE.fontawesome.txt")
        license_files.append("LICENSE.fontawesome.txt")
    providers = list(dict.fromkeys(entry["provider"] for entry in entries))
    catalog = {"schema_version": 1, "brand": "CloudTIX", "provider": ", ".join(providers), "emojis": entries}
    if neutral_pack.exists():
        source_text = "Motive aus den vom Nutzer hochgeladenen emoji.gg-Packs; mit imagegen im grauen Design bearbeitet. Quellen und Zuordnungen stehen bei jedem Emoji im Manifest.\n"
        (PUBLIC / "SOURCE.txt").write_text(source_text, encoding="utf-8")
        catalog["source_information_file"] = "SOURCE.txt"
        zip_entries = [{**entry, "file": entry["name"] + ".png"} for entry in entries]
        with zipfile.ZipFile(PUBLIC / "cloudtix-neutral-emojis.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for entry in entries:
                archive.write(ASSETS / entry["file"], entry["name"] + ".png")
            archive.writestr("emojis.json", json.dumps({**catalog, "emojis": zip_entries}, indent=2, ensure_ascii=False) + "\n")
            archive.writestr("SOURCE.txt", source_text)
            archive.writestr("README.txt", f"CloudTIX: {len(entries)} Emojis mit grauem Hintergrund, hellgrauen Symbolen und erhaltenen Signalfarben.\nPNG: 128 x 128 Pixel. Die PNG-Dateinamen entsprechen den vorgesehenen Discord-Emoji-Namen.\nEin ZIP-Download bestätigt keinen Upload bei Discord; echte IDs sind erst nach dem Upload verfügbar.\n")
    else:
        catalog.update({"license_file": "LICENSE.lucide.txt", "license_files": license_files})
    (PUBLIC / "emojis.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Published {len(entries)} dashboard emoji previews.")


if __name__ == "__main__":
    publish()
