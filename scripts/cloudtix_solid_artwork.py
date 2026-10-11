"""Filled glyphs and vibrant tile palettes for the reference-style emoji pack.

Font Awesome Free 6.7.2 icons are CC BY 4.0; the full bundled license accompanies
the bot assets and dashboard previews. Status overlays remain original vectors.
"""
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree as ET

VERSION = "6.7.2"
BASE = f"https://raw.githubusercontent.com/FortAwesome/Font-Awesome/{VERSION}"

# Lucide semantic names map to filled equivalents without changing saved keys.
GLYPHS = dict(pair.split(":", 1) for pair in """
alarm-clock:bell annoyed:face-dizzy apple:apple-whole archive:box-archive
arrow-down:arrow-down arrow-left:arrow-left arrow-right:arrow-right
arrow-right-left:right-left arrow-up:arrow-up at-sign:at audio-lines:sliders
award:award badge:certificate badge-check:circle-check badge-plus:circle-plus
banknote:money-bill-wave bell:bell binary:hashtag blocks:cubes
book-check:book book-open:book-open bot:robot brain-circuit:brain brick-wall:cubes-stacked
bug:bug cake:cake-candles calendar-check:calendar-check calendar-clock:calendar-days
calendar-days:calendar-days camera:camera car:car cast:chromecast
chart-no-axes-column-increasing:chart-column chart-pie:chart-pie check:check
cherry:apple-whole circle:circle circle-alert:circle-exclamation circle-check:circle-check
circle-dashed:circle circle-dot:circle-dot circle-help:circle-question
circle-minus:circle-minus circle-x:circle-xmark clipboard-list:clipboard-list
clock:clock cloud:cloud code-xml:code coffee:mug-hot coins:coins
contact-round:address-card cookie:cookie-bite copy:copy crown:crown
cup-soda:mug-saucer door-closed:door-closed door-open:door-open download:download
earth:earth-americas external-link:arrow-up-right-from-square eye-off:eye-slash
fast-forward:forward-fast file-search:file-circle-question file-text:file-lines
fingerprint:fingerprint flag:flag flame:fire folder:folder folder-open:folder-open
gamepad-2:gamepad gavel:gavel gem:gem gift:gift globe:globe hand:hand
handshake:handshake hash:hashtag headphones:headphones heart:heart history:clock-rotate-left
house:house image:image inbox:inbox info:circle-info key-round:key key-square:key
landmark:landmark languages:language library-big:book-open-reader life-buoy:life-ring
lightbulb:lightbulb link:link list-checks:list-check list-music:list loader-circle:spinner
lock-keyhole:lock lock-keyhole-open:unlock-keyhole log-in:right-to-bracket
log-out:right-from-bracket mail:envelope medal:medal megaphone:bullhorn menu:bars
message-square-heart:comment-dots message-square-more:comment-dots
message-square-off:comment-slash messages-square:comments mic:microphone
mic-off:microphone-slash monitor:desktop monitor-play:tv moon:moon mountain:mountain
mouse-pointer-2:arrow-pointer music:music notebook-pen:pen-to-square package:box
panel-left-close:angles-left panel-left-open:angles-right panels-top-left:table-columns
party-popper:champagne-glasses pause:pause paw-print:paw pencil:pencil pin:thumbtack
play:play plus:plus radio:radio receipt:receipt repeat:repeat repeat-1:repeat
rewind:backward-fast rocket:rocket rotate-cw:rotate-right save:floppy-disk
scale:scale-balanced scan-line:barcode scissors:scissors scroll-text:scroll search:magnifying-glass
server:server settings:gear shield:shield shield-alert:shield-halved shield-check:shield-halved
shield-off:shield-halved shield-plus:shield shopping-cart:cart-shopping shuffle:shuffle
skip-back:backward-step skip-forward:forward-step smartphone:mobile-screen smile:face-smile
sparkles:wand-magic-sparkles sprout:seedling square:square star:star sticker:note-sticky
store:store target:bullseye ticket:ticket ticket-check:ticket ticket-plus:ticket ticket-x:ticket
timer:stopwatch trash-2:trash-can triangle-alert:triangle-exclamation trophy:trophy
upload:upload user-round:user user-round-minus:user-minus user-round-plus:user-plus
users:users users-round:user-group video:video volume-2:volume-high volume-x:volume-xmark
wallet:wallet wifi:wifi wrench:screwdriver-wrench x:xmark zap:bolt
paintbrush:paintbrush github:github-alt youtube:youtube
""".split())
# Chromecast is a brand glyph, unlike all other filled icons.
FOLDERS = {"cast": "brands", "github": "brands", "youtube": "brands"}

CATEGORY_COLORS = {
    "Security": ("#12c8ff", "#0095f2", "#b8f5ff"),
    "Moderation": ("#704dff", "#4730f3", "#d5caff"),
    "Support": ("#4484ff", "#3155ef", "#c9e3ff"),
    "Community": ("#b22cff", "#8310f8", "#eccaff"),
    "Music": ("#fb36af", "#e9088f", "#ffd0ef"),
    "Badges": ("#ffd126", "#ffa600", "#fff0a5"),
    "Status": ("#14dfab", "#00c790", "#b4ffe8"),
    "Server": ("#3f9bff", "#1374f6", "#c4e5ff"),
    "Regelwerk": ("#a778ff", "#8045f3", "#efddff"),
    "Economy": ("#ffd626", "#ffb500", "#fff3b2"),
    "Media": ("#ed42fa", "#c912eb", "#fdd4ff"),
    "UI": ("#628aff", "#4359fc", "#d4e2ff"),
}
SPECIAL_COLORS = {
    "premium": ("#ff26ed", "#f100da", "#ffd2fa"),
    "boost": ("#ff29ee", "#eb00d7", "#ffd1f8"),
    "server_boost": ("#ff29ee", "#eb00d7", "#ffd1f8"),
    "bot": ("#292929", "#101010", "#e4e4e4"),
    "bot_add": ("#292929", "#101010", "#e4e4e4"),
    "support": ("#292082", "#09014f", "#c7c4ff"),
    "help": ("#292082", "#09014f", "#c7c4ff"),
    "crown": ("#ffc620", "#ffa900", "#fff0b5"),
    "owner": ("#ffc620", "#ffa900", "#fff0b5"),
    "server_owner": ("#ffc620", "#ffa900", "#fff0b5"),
    "tools": ("#fff62d", "#ffdf00", "#ffff9b"),
    "heart": ("#ff6ce3", "#ff35ce", "#ffd4f5"),
    "event": ("#ff3881", "#f50b62", "#ffbedb"),
    "party": ("#ff3881", "#f50b62", "#ffbedb"),
    "developer": ("#6254ff", "#4933ff", "#cfc7ff"),
    "ticket": ("#ededed", "#c9c9d2", "#ffffff"),
    "trophy": ("#bdff60", "#a2ff45", "#4fa600"),
    "rank": ("#bdff60", "#a2ff45", "#4fa600"),
    "star": ("#ffd33d", "#ffb400", "#fff2a3"),
    "offline": ("#686978", "#454653", "#dedee6"),
    "booster": ("#ff26ed", "#f100da", "#ffd2fa"),
    "github": ("#171717", "#080808", "#ffffff"),
    "youtube": ("#ff5757", "#ff2525", "#ffffff"),
    "paint": ("#ff222a", "#ed0013", "#ffbfc6"),
    "partner": ("#11ffb9", "#00e9a1", "#bdffe9"),
    "supporter": ("#a72aff", "#8110ff", "#ebc9ff"),
    "ambassador": ("#b6ff69", "#8ef942", "#4fa800"),
}

def glyph_name(vector):
    if vector not in GLYPHS:
        raise ValueError(f"No filled glyph mapped for {vector}")
    return GLYPHS[vector]

def glyph_url(vector):
    return f"{BASE}/svgs/{FOLDERS.get(vector, 'solid')}/{glyph_name(vector)}.svg"

def source(vector, assets: Path):
    target = assets / "filled-sources" / f"{vector}.svg"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(glyph_url(vector), timeout=30) as response:
            target.write_bytes(response.read())
    return vector, target.read_bytes()

def install_license(assets: Path):
    target = assets / "LICENSE.fontawesome.txt"
    if not target.exists():
        with urlopen(f"{BASE}/LICENSE.txt", timeout=30) as response:
            target.write_bytes(response.read())
    return target

def palette(style, category, label, shade, positive):
    if style == "gray":
        foreground = {"yellow": "#ffe276", "red": "#ff9ca2"}.get(shade, "#ededf2")
        return "#45454b", "#29292f", foreground
    if shade == "yellow":
        return "#ffd326", "#ffb000", "#fff1a9"
    if shade == "red":
        return "#ff363b", "#f50016", "#ffd2d4"
    if label in SPECIAL_COLORS:
        return SPECIAL_COLORS[label]
    if label in positive:
        return "#67ff13", "#2ae900", "#e1ffc1"
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS["UI"])


def artwork(vector, shade, style, category, label, marks, positive):
    root = ET.fromstring(vector)
    viewbox = root.get("viewBox", "0 0 512 512")
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    geometry = "".join(ET.tostring(child, encoding="unicode") for child in root)
    if label == "exclamation":
        viewbox = "0 0 24 24"
        geometry = '<rect x="10" y="2" width="4" height="13" rx="2"/><circle cx="12" cy="21" r="2"/>'
    top, bottom, foreground = palette(style, category, label, shade, positive)
    symbol_bottom = foreground if style == "color" else "#b4b4bf"
    if style == "color":
        foreground, symbol_bottom = {
            "tools": ("#fff340", "#f0d600"),
            "bot": ("#c9c9cf", "#97979f"),
            "bot_add": ("#c9c9cf", "#97979f"),
            "trophy": ("#79ff08", "#4bce00"),
            "rank": ("#79ff08", "#4bce00"),
            "ambassador": ("#79ff08", "#4bce00"),
            "developer": ("#a69aff", "#8878ff"),
            "crown": ("#fff19a", "#efb41a"),
            "owner": ("#fff19a", "#efb41a"),
            "server_owner": ("#fff19a", "#efb41a"),
        }.get(label, (foreground, symbol_bottom))
    mark = marks.get(label)
    mark_paths = {
        "check": '<path d="m93 100 5 5 9-10"/>',
        "cross": '<path d="m94 96 11 11m0-11-11 11"/>',
        "minus": '<path d="M93 102h14"/>',
        "plus": '<path d="M93 102h14m-7-7v14"/>',
        "clock": '<circle cx="100" cy="102" r="7"/><path d="M100 97v5l4 2"/>',
        "refresh": '<path d="M94 103a6 6 0 1 0 2-6m-2-3v5h5"/>',
        "alert": '<path d="M100 95v8m0 5v.1"/>',
        "dot": '<circle cx="100" cy="102" r="3" fill="#ffffff"/>',
    }
    badge = (f'<circle cx="100" cy="102" r="15" fill="{bottom}" stroke="#ffffff" stroke-opacity=".4"/>'
             f'<g fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">{mark_paths[mark]}</g>') if mark else ""
    sparkles = ('<path d="M19 23q0 5 5 5-5 0-5 5 0-5-5-5 5 0 5-5Z"/>'
                '<path d="M106 88q0 5 5 5-5 0-5 5 0-5-5-5 5 0 5-5Z"/>') if label in {"premium", "boost", "star", "reward"} else ""
    # Only the icon glows. The filled motif stays sharp above its soft halo.
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2=".6" y2="1">
      <stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
    <radialGradient id="light" cx=".3" cy=".2" r=".8">
      <stop stop-color="#ffffff" stop-opacity=".13"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="ambient">
      <stop stop-color="{foreground}" stop-opacity=".28"/><stop offset="1" stop-color="{foreground}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="ink" x1="0" y1="0" x2=".4" y2="1">
      <stop stop-color="{foreground}"/><stop offset="1" stop-color="{symbol_bottom}"/>
    </linearGradient>
    <filter id="halo" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="5"/>
    </filter>
    <filter id="depth" x="-40%" y="-40%" width="180%" height="180%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000000" flood-opacity=".35"/>
    </filter>
    <clipPath id="tile"><rect x="4" y="4" width="120" height="120" rx="36"/></clipPath>
  </defs>
  <g clip-path="url(#tile)">
    <rect x="4" y="4" width="120" height="120" rx="36" fill="url(#background)"/>
    <rect x="4" y="4" width="120" height="120" rx="36" fill="url(#light)"/>
    <ellipse cx="64" cy="64" rx="48" ry="48" fill="url(#ambient)"/>
    <g id="rotation">
      <g filter="url(#halo)" opacity=".6"><svg x="25" y="25" width="78" height="78" viewBox="{viewbox}" overflow="visible" fill="{foreground}">{geometry}</svg></g>
      <g filter="url(#depth)"><svg x="25" y="25" width="78" height="78" viewBox="{viewbox}" overflow="visible" fill="url(#ink)">{geometry}</svg></g>
    </g>
    <g fill="#ffffff" opacity=".9">{sparkles}</g>
    {badge}
  </g>
</svg>'''
