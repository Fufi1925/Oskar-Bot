"""Shared names and search terms for the expanded CloudTIX emoji collection."""

# key | Lucide icon | category | Unicode fallback | German name | search terms
ROWS = """
exclamation|circle-alert|UI|❗|Ausrufezeichen|! wichtig achtung alert attention
question|circle-help|UI|❓|Fragezeichen|? frage question
globe|earth|UI|🌍|Welt|welt world global internet globe
globe_languages|languages|UI|🌐|Sprachen|übersetzung translation language international
member|user-round|Community|👤|Mitglied|member user person nutzer
member_verified|user-round|Community|✅|Verifiziertes Mitglied|verified member bestätigt
member_add|user-round-plus|Community|➕|Mitglied hinzufügen|add member einladen
member_remove|user-round-minus|Community|➖|Mitglied entfernen|remove member
member_banned|user-round|Moderation|🚫|Gebanntes Mitglied|banned member ban sperre
user_profile|contact-round|Community|👤|Profil|profile account konto
text_channel|hash|Server|#️⃣|Textkanal|text channel chat kanal
voice_channel|volume-2|Server|🔊|Sprachkanal|voice channel sprachchat
forum_channel|messages-square|Server|💬|Forum|forum channel diskussion
stage_channel|mic|Server|🎤|Bühne|stage channel bühnenkanal
category_folder|folder|Server|📁|Kategorie|category folder ordner
thread|message-square-more|Server|💬|Thread|thread beitrag unterhaltung
unban|gavel|Moderation|✅|Entbannen|unban entsperren ban aufheben
softban|gavel|Moderation|🔨|Softban|soft ban softban
tempban|gavel|Moderation|⏳|Temporärer Ban|tempban ban zeitlich zeitban
mute_member|mic-off|Moderation|🔇|Stummschalten|mute member stumm
unmute_member|mic|Moderation|🎤|Stummschaltung aufheben|unmute member
remove_timeout|timer|Moderation|✅|Timeout aufheben|untimeout timeout entfernen
warn_remove|shield-alert|Moderation|✅|Verwarnung entfernen|unwarn warn remove
warn_list|clipboard-list|Moderation|📋|Verwarnungen|warns warnings warn list
mod_log|scroll-text|Moderation|📜|Moderationsprotokoll|modlog moderation logs verlauf
appeal|scale|Moderation|⚖️|Einspruch|appeal beschwerde ban appeal
evidence|file-search|Moderation|🔎|Beweise|evidence proof nachweis
slowmode|timer|Moderation|⏱️|Slowmode|slow mode langsam cooldown
nsfw|eye-off|Moderation|🔞|NSFW|nsfw adult jugendschutz
anti_spam|message-square-off|Moderation|🛡️|Anti-Spam|spam antispam flood
anti_raid|shield-alert|Moderation|🛡️|Anti-Raid|raid antiraid schutz
purge|trash-2|Moderation|🗑️|Nachrichten löschen|purge clear chat mass delete
server|server|Server|🖥️|Server|guild discord server
server_settings|settings|Server|⚙️|Server-Einstellungen|guild settings config konfiguration
server_stats|chart-no-axes-column-increasing|Server|📊|Server-Statistik|stats statistik zahlen
server_boost|rocket|Server|🚀|Server-Boost|boost booster nitro
server_owner|crown|Server|👑|Server-Inhaber|owner inhaber besitzer
admin|shield-check|Server|🛡️|Administrator|admin administrator verwaltung
moderator|shield|Server|🛡️|Moderator|moderator mod moderation
staff|users-round|Server|👥|Team|staff team helfer
newcomer|sprout|Server|🌱|Neues Mitglied|newcomer new member neu
bot_add|bot|Server|🤖|Bot hinzufügen|add bot invite einladen
server_join|log-in|Server|📥|Server beitreten|join server beitritt
server_leave|log-out|Server|📤|Server verlassen|leave server austritt
goodbye|door-open|Server|👋|Verabschiedung|goodbye bye farewell tschüss
welcome_wave|hand|Server|👋|Willkommensgruß|welcome wave willkommen begrüßung hallo
bug_report|bug|Support|🐞|Bug melden|bug report fehler melden
suggestion|lightbulb|Support|💡|Vorschlag|suggestion idee verbesserung
help|life-buoy|Support|🛟|Hilfe|help support hilfe
ticket_reopen|ticket-plus|Support|🎫|Ticket wieder öffnen|ticket reopen wiedereröffnen
ticket_transfer|arrow-right-left|Support|↔️|Ticket übertragen|ticket transfer weiterleiten
ticket_archive|archive|Support|🗃️|Ticket archivieren|ticket archive archiv
ticket_priority|flag|Support|🚩|Dringendes Ticket|ticket priority dringend priorität
ticket_pending|clock|Support|🕒|Wartendes Ticket|ticket pending warten offen
ticket_resolved|ticket|Support|✅|Gelöstes Ticket|ticket resolved erledigt gelöst
ticket_category|folder-open|Support|📂|Ticket-Kategorie|ticket category bereich
rules_violation|book-open|Regelwerk|🚫|Regelverstoß|rules violation regelbruch
rules_update|book-open|Regelwerk|📖|Regeln aktualisieren|rules update änderung
rules_pending|book-open|Regelwerk|📖|Regeln noch nicht akzeptiert|rules pending zustimmung
age_limit|circle-alert|Regelwerk|🔞|Altersgrenze|age limit mindestalter 18 16
agreement|handshake|Regelwerk|🤝|Zustimmung|agreement accept einverständnis
announcement_rules|megaphone|Regelwerk|📣|Regel-Ankündigung|rules announcement bekanntmachung
wallet|wallet|Economy|👛|Geldbörse|wallet balance guthaben
coins|coins|Economy|🪙|Münzen|coins geld money
bank|landmark|Economy|🏦|Bank|bank konto sparen
shop|store|Economy|🏪|Shop|shop laden kaufen
cart|shopping-cart|Economy|🛒|Warenkorb|cart einkauf bestellen
reward|award|Economy|🏅|Belohnung|reward preis bonus
daily|calendar-check|Economy|📅|Tägliche Belohnung|daily streak täglich
trade|arrow-right-left|Economy|🔄|Handel|trade tausch transfer
inventory|package|Economy|📦|Inventar|inventory items gegenstände
receipt|receipt|Economy|🧾|Beleg|receipt rechnung kauf
party|party-popper|Community|🎉|Party|party feiern celebration
fire|flame|Community|🔥|Feuer|fire hot trend
gift_claim|gift|Community|🎁|Geschenk abholen|gift claim giveaway gewinn
timer_event|alarm-clock|Community|⏰|Event-Erinnerung|event timer reminder erinnerung
image|image|Media|🖼️|Bild|image picture foto
camera|camera|Media|📷|Kamera|camera photo foto
video|video|Media|📹|Video|video film
streaming|monitor-play|Media|📺|Stream|streaming livestream twitch
maintenance|wrench|Status|🔧|Wartung|maintenance reparatur update
outage|circle-x|Status|❌|Störung|outage down offline fehler
scheduled|calendar-clock|Status|📅|Geplant|scheduled geplant termin
complete|circle-check|Status|✅|Abgeschlossen|complete done fertig erledigt
booster|gem|Badges|💎|Booster|boost booster nitro diamant
paint|paintbrush|Media|🎨|Design|paint design farbe pinsel malen
github|github|Media|💻|GitHub|github git code repository
youtube|youtube|Media|▶️|YouTube|youtube video kanal
partner|link|Badges|🤝|Partner|partner partnership partnerschaft
supporter|heart|Badges|💜|Unterstützer|supporter apoiador unterstützer
ambassador|users|Badges|🌟|Botschafter|ambassador embaixador botschafter
rocket|rocket|Community|🚀|Rakete|rocket rakete start launch
trophy|trophy|Community|🏆|Pokal|trophy pokal sieger gewinnen
"""

EXPANDED = [tuple(line.split("|")) for line in ROWS.strip().splitlines()]
NEW_SPECS = [(key, vector, category, fallback, f"CATALOG_{key.upper()}")
             for key, vector, category, fallback, *_ in EXPANDED]
NEW_LABELS = {key: label for key, _, _, _, label, _ in EXPANDED}
KEYWORDS = {key: words.split() for key, _, _, _, _, words in EXPANDED}

# German labels make all existing entries findable without knowing code names.
ORIGINAL_LABELS = """
shield|Schutzschild
anti_nuke|Anti-Nuke
automod|Automatische Moderation
jail|Gefängnis
ticket|Ticket
verification|Verifizierung
applications|Bewerbungen
level|Level
rank|Rang
giveaway|Gewinnspiel
welcome|Willkommen
play|Wiedergabe
pause|Pause
headphones|Kopfhörer
volume|Lautstärke
checkmark|Häkchen
cross|Kreuz
arrow|Pfeil rechts
info|Information
warning|Warnung
loading|Laden
back|Zurück
stop|Stopp
skip|Nächster Titel
previous|Vorheriger Titel
settings|Einstellungen
members|Mitglieder
message|Nachrichten
refresh|Aktualisieren
plus|Plus
delete|Löschen
mute|Ton aus
unlock|Entsperren
star|Stern
cloud|Wolke
ban|Ban
kick|Kick
timeout|Timeout
warn|Verwarnung
audit_log|Audit-Log
permissions|Berechtigungen
firewall|Firewall
quarantine|Quarantäne
scan|Scan
fingerprint|Fingerabdruck
password|Passwort
incognito|Unsichtbar
lockdown|Sperren
protection|Zusätzlicher Schutz
report|Melden
ticket_open|Ticket öffnen
ticket_close|Ticket schließen
ticket_claim|Ticket übernehmen
transcript|Transkript
support|Support
faq|Häufige Fragen
mail|E-Mail
inbox|Posteingang
form|Formular
accept|Akzeptieren
reject|Ablehnen
feedback|Feedback
boost|Boost
birthday|Geburtstag
event|Event
announcement|Ankündigung
invite|Einladung
leave|Verlassen
role|Rolle
leaderboard|Bestenliste
xp|Erfahrungspunkte
poll|Umfrage
counting|Zählen
heart|Herz
game|Spiele
crown|Krone
premium|Premium
shuffle|Zufällige Wiedergabe
repeat|Wiederholen
repeat_one|Titel wiederholen
queue|Warteschlange
playlist|Playlist
note|Musiknote
microphone|Mikrofon
microphone_off|Mikrofon aus
voice|Sprachchat
equalizer|Equalizer
seek_forward|Vorspulen
rewind|Zurückspulen
home|Startseite
dashboard|Dashboard
channel|Kanal
search|Suche
edit|Bearbeiten
save|Speichern
copy|Kopieren
download|Herunterladen
upload|Hochladen
link|Link
external_link|Externer Link
arrow_up|Pfeil hoch
arrow_down|Pfeil runter
menu|Menü
close_panel|Panel schließen
open_panel|Panel öffnen
notification|Benachrichtigung
pin|Anpinnen
clock|Uhr
bot|Bot
tools|Werkzeuge
bug_hunter|Bug-Hunter
developer|Entwickler
hypesquad|HypeSquad
browser|Browser
owner|Inhaber
mention|Erwähnung
new|Neu
pc|Computer
mobile|Handy
connection|Verbindung
ai|Künstliche Intelligenz
module|Module
seed|Keimling
thunder|Blitz
circle|Kreis
online|Online
offline|Offline
idle|Abwesend
dnd|Nicht stören
cast|Übertragen
cute|Lächeln
panda|Tierpfote
dance|Tanzen
sticker|Sticker
racecar|Auto
tea|Tee
cherries|Kirschen
cookie|Keks
cursor|Mauszeiger
dizzy|Benommen
coffee|Kaffee
money|Geld
moon|Mond
peach|Frucht
rock|Berg
scissors|Schere
shocked|Überrascht
target|Ziel
"""
LABELS = dict(line.split("|", 1) for line in ORIGINAL_LABELS.strip().splitlines())
LABELS.update(NEW_LABELS)
KEYWORDS.update({
    "welcome": ["willkommen", "welcome", "hallo", "begrüßung"],
    "members": ["member", "members", "mitglieder", "users"],
    "warning": ["!", "warn", "warning", "achtung"],
    "warn": ["warn", "warns", "warnings", "verwarnen"],
    "ban": ["ban", "bans", "bann", "sperren", "bannen"],
    "rules": ["regelwerk", "regeln", "rules", "regelbuch"],
    "browser": ["welt", "world", "globe", "web", "internet"],
})

# A small corner mark distinguishes related workflow symbols at a glance.
MARKS = {
    "member_verified": "check", "member_banned": "cross",
    "softban": "minus", "tempban": "clock", "unban": "check",
    "warn_remove": "minus", "remove_timeout": "check",
    "bot_add": "plus", "server_settings": "dot", "server_boost": "plus",
    "ticket_reopen": "refresh", "ticket_pending": "clock",
    "ticket_resolved": "check", "ticket_priority": "alert",
    "rules_violation": "cross", "rules_update": "refresh",
    "rules_pending": "clock", "gift_claim": "check", "timer_event": "clock",
}
