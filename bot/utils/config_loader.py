# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

import yaml
import json
import os

# All paths are resolved relative to the bot package so the loader keeps
# working no matter which directory the process was started from.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = os.path.join(BASE_DIR, "config.yml")
LANG_DIRECTORY = os.path.join(BASE_DIR, "lang")
INSTRUCTIONS_DIRECTORY = os.path.join(BASE_DIR, "instructions")
CHANNELS_PATH = os.path.join(BASE_DIR, "channels.json")

DEFAULT_CONFIG = {
    "LANGUAGE": "en",
    "INTERNET_ACCESS": False,
    "MAX_SEARCH_RESULTS": 4,
    "MAX_HISTORY": 8,
}

# Config load
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}
except (FileNotFoundError, yaml.YAMLError) as exc:
    print(f"[config_loader] Could not read config.yml ({exc}); using defaults.")
    config = {}

for key, value in DEFAULT_CONFIG.items():
    config.setdefault(key, value)

## Language settings ##
valid_language_codes = []
lang_directory = LANG_DIRECTORY

current_language_code = config["LANGUAGE"]

if os.path.isdir(lang_directory):
    for filename in os.listdir(lang_directory):
        if (
            filename.startswith("lang.")
            and filename.endswith(".json")
            and os.path.isfile(os.path.join(lang_directory, filename))
        ):
            valid_language_codes.append(filename.split(".")[1])

# Fall back to a language that actually exists on disk.
if valid_language_codes and current_language_code not in valid_language_codes:
    print(
        f"[config_loader] Language '{current_language_code}' not found, "
        f"falling back to '{valid_language_codes[0]}'."
    )
    current_language_code = valid_language_codes[0]


def load_current_language() -> dict:
    """Load the active language file. Returns {} when unavailable."""
    lang_file_path = os.path.join(lang_directory, f"lang.{current_language_code}.json")
    try:
        with open(lang_file_path, encoding="utf-8") as lang_file:
            return json.load(lang_file)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[config_loader] Could not load language file: {exc}")
        return {}


# Instructions loader
def load_instructions() -> dict:
    """
    Load AI instruction snippets from instructions/*.txt.

    The directory is optional — a missing folder yields an empty mapping
    instead of raising FileNotFoundError.
    """
    instructions = {}
    if not os.path.isdir(INSTRUCTIONS_DIRECTORY):
        return instructions

    for file_name in os.listdir(INSTRUCTIONS_DIRECTORY):
        if not file_name.endswith(".txt"):
            continue
        file_path = os.path.join(INSTRUCTIONS_DIRECTORY, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                instructions[file_name.split(".")[0]] = file.read()
        except OSError as exc:
            print(f"[config_loader] Could not read {file_name}: {exc}")
    return instructions


def load_active_channels() -> dict:
    """
    Load the active AI channels mapping.

    Previously this returned an unbound local variable when channels.json was
    missing, raising UnboundLocalError. Now it returns an empty mapping.
    """
    if not os.path.exists(CHANNELS_PATH):
        return {}
    try:
        with open(CHANNELS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[config_loader] Could not read channels.json: {exc}")
        return {}