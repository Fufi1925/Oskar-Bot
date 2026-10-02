#!/usr/bin/env python3
"""Läuft der echte Bot-Code gegen gefälschte Discord-Objekte.

Statische Prüfungen sehen nur, dass eine Funktion existiert. Hier läuft sie:
Modal vor `defer()`, Ticketkanal mit sicherem Namen, Platzhalter im Text,
Übernehmen/Schließen mit Transkript, Spam-Serie, Giveaway-Abschluss,
Herzschlag. Kein Gateway — nur die Attribute, die discord.py an den
betreffenden Stellen liest.
"""
import asyncio
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path(tempfile.gettempdir()) / "lbost-botlauf.sqlite3"
for suffix in ("", "-wal", "-shm"):
    Path(str(DB) + suffix).unlink(missing_ok=True)
os.environ.update({
    "LBOST_SHOP_DB_PATH": str(DB),
    "LBOST_SHOP_SECRET_KEY": "lauf-secret",
    "LBOST_SHOP_TOKEN_ENCRYPTION_KEY": "lauf-token-secret",
})

import discord  # noqa: E402

from lbost_shop_app import db, automation as automation_store  # noqa: E402
from lbost_shop_app.config import get_settings  # noqa: E402
from lbost_shop_bot.client import ShopBot, layout, taugliche_teilnehmer  # noqa: E402

settings = get_settings()
db.init_features(settings)


# ── Unterbau ───────────────────────────────────────────────────────────
def text_aus_view(view) -> str:
    """Alle TextDisplay-Abschnitte einer Components-V2-Ansicht als Text."""
    funde: list[str] = []

    def sammeln(obj):
        for kind in getattr(obj, "children", None) or []:
            inhalt = getattr(kind, "content", None)
            if isinstance(inhalt, str):
                funde.append(inhalt)
            sammeln(kind)

    sammeln(view)
    return "\n".join(funde)


def knopfe_aus_view(view) -> list[str]:
    """Beschriftungen aller Buttons in einer Ansicht, in Reihenfolge."""
    funde: list[str] = []

    def sammeln(obj):
        for kind in getattr(obj, "children", None) or []:
            beschriftung = getattr(kind, "label", None)
            if isinstance(beschriftung, str):
                funde.append(beschriftung)
            sammeln(kind)

    sammeln(view)
    return funde


def meldung_text(interaction) -> str:
    """Was der Nutzer als ephemere Rückmeldung sieht (egal wann gesendet)."""
    if interaction.response.sent is not None:
        return text_aus_view(interaction.response.sent)
    return text_aus_view(interaction.followups[-1]) if interaction.followups else ""


class FakeMember:
    def __init__(self, user_id=7001, name="fufi", global_name="Fufi", rollen=None, admin=False, bot=False):
        self.id = user_id
        self.bot = bot
        self.name = name
        self.global_name = global_name
        self.roles = list(rollen or [])
        self.top_role = FakeRole(3, "Bot", 3)
        self.guild_permissions = type("Berechtigungen", (), {
            "manage_messages": admin, "manage_channels": admin, "moderate_members": admin,
            "kick_members": admin, "ban_members": admin, "administrator": admin,
        })()
        self.timeouts: list = []
        self.added: list = []
        self.removed: list = []

    def __str__(self):
        return self.name

    def is_timed_out(self):
        return False

    async def timeout(self, dauer, *, reason=None):
        self.timeouts.append((dauer, reason))

    async def add_roles(self, *rollen, reason=None):
        self.added.extend(rollen)
        self.roles.extend(rollen)

    async def remove_roles(self, *rollen, reason=None):
        self.removed.extend(rollen)


class FakeRole:
    def __init__(self, rolle_id, name, position=1):
        self.id = rolle_id
        self.name = name
        self.position = position
        self.mention = f"<@&{rolle_id}>"
        self.managed = False

    def is_default(self):
        return self.id == 1

    def __ge__(self, other):
        return self.position >= getattr(other, "position", 0)


class FakeMessage:
    def __init__(self, author, content="", channel=None, kennung=0):
        self.author = author
        self.content = content
        self.clean_content = content
        self.channel = channel
        self.guild = channel.guild if channel else None
        self.id = 900 + kennung
        self.attachments = []
        self.created_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.geloescht = False

    async def delete(self):
        self.geloescht = True


class FakeChannel:
    def __init__(self, guild, kanal_id=500, name="allgemein"):
        self.id = kanal_id
        self.name = name
        self.guild = guild
        self.nachrichten: list[FakeMessage] = []
        self.ansichten: list = []
        self.dateien: list = []
        self.restrictions = None
        self.slowmode = None
        self.kategorie = None
        self.ueberschreibungen = None
        self.deleted = False

    async def delete(self, **kwargs):
        self.deleted = True

    async def send(self, content=None, *, view=None, file=None):
        self.ansichten.append(view)
        if file is not None:
            self.dateien.append(file)
        nachricht = FakeMessage(FakeMember(2, "bot", "Bot"), content or "", self, len(self.nachrichten))
        self.nachrichten.append(nachricht)
        return nachricht

    async def set_permissions(self, member, **rechte):
        self.restrictions = (member.id, rechte)

    def history(self, *, limit=None, before=None, oldest_first=False):
        async def generator():
            for nachricht in list(self.nachrichten):
                if before is not None and nachricht.id >= before.id:
                    continue
                yield nachricht

        return generator()

    @property
    def mention(self):
        return f"<#{self.id}>"


def fake_category(kanal_id, name, guild):
    """Echte discord.py-Klasse ohne Konstruktor — der Bot prüft isinstance."""
    kategorie = discord.CategoryChannel.__new__(discord.CategoryChannel)
    kategorie.id = kanal_id
    kategorie.name = name
    kategorie.guild = guild
    return kategorie


class FakeGuild:
    def __init__(self, guild_id=11, name="Test Guild", kanale=None, rollen=None, mitglieder=None):
        self.id = guild_id
        self.name = name
        self._kanale = {k.id: k for k in (kanale or [])}
        self._rollen = {r.id: r for r in (rollen or [])}
        self.members = mitglieder or []
        self.default_role = FakeRole(1, "@everyone", 0)
        self.owner_id = 1
        self.me = FakeMember(2, "bot", "Bot", admin=True, bot=True)

    def get_channel(self, kanal_id):
        return self._kanale.get(kanal_id)

    def get_role(self, rolle_id):
        return self._rollen.get(rolle_id)

    def get_member(self, user_id):
        return next((m for m in self.members if m.id == user_id), None)

    async def create_text_channel(self, name, *, category=None, overwrites=None, reason=None, slowmode_seconds=0):
        # Discord lehnt Namen mit Sonderzeichen ab - hier dieselbe Schranke,
        # damit ein kaputter Kanalname nicht durchläuft.
        assert all(ch in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in name), f"abgelehnter Name: {name!r}"
        assert len(name) <= 100
        kanal = FakeChannel(self, 700 + len(self._kanale), name)
        kanal.slowmode = slowmode_seconds
        kanal.ueberschreibungen = overwrites
        kanal.kategorie = category
        self._kanale[kanal.id] = kanal
        return kanal

    def ticket_kanaele(self):
        return [k for k in self._kanale.values() if str(k.name).startswith("ticket-")]


class FakeResponse:
    def __init__(self):
        self.reihenfolge: list[str] = []
        self.deferred = False
        self.modal = None
        self.sent = None

    def is_done(self):
        return self.deferred or self.modal is not None or self.sent is not None

    async def defer(self, *, ephemeral=False):
        assert self.modal is None, "defer() nach dem Modal"
        self.deferred = True
        self.reihenfolge.append("defer")

    async def send_message(self, *, view=None, ephemeral=False):
        self.sent = view
        self.reihenfolge.append("send_message")

    async def send_modal(self, modal):
        assert not self.deferred, "Discord lehnt ein Modal nach defer() ab"
        self.modal = modal
        self.reihenfolge.append("modal")


class FakeFollowup:
    def __init__(self):
        self.ansichten: list = []

    async def send(self, *, view=None, ephemeral=False):
        self.ansichten.append(view)


class FakeInteraction:
    def __init__(self, guild, user, channel=None):
        self.guild = guild
        self.user = user
        self.channel = channel or FakeChannel(guild)
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {}
        self.id = 4242

    @property
    def followups(self):
        return self.followup.ansichten


async def main() -> None:
    bot = ShopBot(settings)
    # ``user`` ist ein Read-only-Property des Connection-Objekts
    bot._connection.user = FakeMember(2, "bot", "Bot", bot=True)
    bot._cooldowns = {}

    # ── Konfiguration, so wie das Dashboard sie schreibt ─────────────
    db.set_feature(11, "tickets", {
        "enabled": True, "panel_channel_id": "500", "category_id": "600", "log_channel_id": "601",
        "support_role_ids": "40", "open_role_ids": "", "mention_support": True, "slowmode_seconds": 10,
        "ticket_title": "Ticket {ticket_number} für {user}",
        "ticket_message": "Hallo {user}, {server} hilft. Kanal: {channel}. Kategorie {category}.",
        "ticket_created_message": "Offen: {channel} ({ticket_number})",
        "questions_json": [
            {"label": "Worum?", "type": "short", "required": True},
            {"label": "Was ist passiert?", "type": "paragraph", "required": False},
            {"label": "Beleg", "type": "image", "required": False},
        ],
        "color": "#ff0000",
    }, 1, settings)

    rolle = FakeRole(40, "Support", 2)   # unter dem Bot -> vergebenbar
    hoeher = FakeRole(42, "Admins", 9)   # ueber dem Bot -> abgelehnt
    log = FakeChannel(None, 601, "protokoll")  # nicht "ticket-*", das zaehlt mit
    guild = FakeGuild(11, "Test Guild ÄÖÜ", [log], [rolle, hoeher], [])
    kategorie = fake_category(600, "Support", guild)
    log.guild = guild
    guild._kanale[600] = kategorie
    nutzer = FakeMember(7001, "fufi.dev", "Fufi | Dev", [guild.default_role, rolle])

    # 1) Fragen vorhanden -> erst das Modal, kein defer vorher
    lauf = FakeInteraction(guild, nutzer)
    await bot.start_ticket(lauf, "default")
    assert lauf.response.reihenfolge == ["modal"], lauf.response.reihenfolge
    eingaben = [kind for kind in lauf.response.modal.children if isinstance(kind, discord.ui.TextInput)]
    uploading = [kind for kind in lauf.response.modal.children if isinstance(kind, discord.ui.Label)]
    assert len(eingaben) == 2, [type(k).__name__ for k in lauf.response.modal.children]
    assert eingaben[0].required is True and eingaben[1].required is False
    assert eingaben[0].style == discord.TextStyle.short and eingaben[0].max_length == 200
    assert eingaben[1].style == discord.TextStyle.paragraph and eingaben[1].max_length == 1000
    assert len(uploading) == 1 and isinstance(uploading[0].component, discord.ui.FileUpload), \
        "Bildfrage kein Datei-Upload"
    assert len(lauf.response.modal.children) == 3, "Fragenzahl im Modal vertauscht"

    # 2) Ticket: sicherer Name, Kategorie, Slowmode, Rechte, Platzhalter, Antwort
    await bot.create_ticket(lauf, "default", antworten=[{"label": "Worum?", "type": "short", "value": "Login geht nicht"}])
    tickets = guild.ticket_kanaele()
    assert len(tickets) == 1, tickets
    kanal = tickets[0]
    assert kanal.name == "ticket-0001-fufi-dev", kanal.name
    assert kanal.slowmode == 10, "Slowmode nicht uebernommen"
    assert kanal.kategorie is kategorie, "Kategorie nicht gesetzt"
    rechte = {getattr(objekt, "id", None): overwritten for objekt, overwritten in kanal.ueberschreibungen.items()}
    assert rechte[guild.default_role.id].view_channel is False, "everyone kann das Ticket lesen"
    assert rechte[nutzer.id].view_channel is True and rechte[nutzer.id].send_messages is True
    assert rechte[rolle.id].view_channel is True, "Support-Rolle hat keinen Zugriff"
    assert rechte[guild.me.id].manage_channels is True, "Bot darf den Kanal nicht auflösen"
    zeile = db.ticket_fuer_kanal(kanal.id, settings)
    assert zeile["status"] == "open" and zeile["ticket_number"] == 1
    assert "Login geht nicht" in zeile["answers_json"]
    text = text_aus_view(kanal.ansichten[0])
    assert "Ticket 0001 für <@7001>" in text, text[:200]
    assert "Hallo <@7001>, Test Guild ÄÖÜ hilft." in text, text
    assert "Kategorie Support" in text and "#ticket-0001-fufi-dev" in text, text
    assert "**Worum?**" in text and "Login geht nicht" in text, "Antwort fehlt im Tickettext"
    assert knopfe_aus_view(kanal.ansichten[0]) == ["Claim", "Unclaim", "Lock", "Unlock", "Close"], knopfe_aus_view(kanal.ansichten[0])
    assert "Support angefragt" in text_aus_view(kanal.ansichten[1]), "Support nicht erwähnt"
    assert "Offen: #ticket-0001-fufi-dev (0001)" in meldung_text(lauf), meldung_text(lauf)

    # 3) Zweites offenes Ticket derselben Person: abgelehnt, kein neuer Kanal
    zweiter = FakeInteraction(guild, nutzer)
    await bot.create_ticket(zweiter, "default")
    assert len(guild.ticket_kanaele()) == 1, "zweites Ticket angelegt"
    assert "Ticket-Limit erreicht" in meldung_text(zweiter), meldung_text(zweiter)

    # 3b) Panel mit Rollenpflicht: ohne Rolle kein Ticket, kein Kanal
    bot.feature_cache.clear()
    db.set_feature(11, "tickets", {**db.get_feature(11, "tickets", settings), "open_role_ids": "40"},
                   1, settings, audit=False)
    nur_jeder = FakeMember(7050, "ohnerolle", "Ohne Rolle", [guild.default_role])
    abgewehrt = FakeInteraction(guild, nur_jeder)
    await bot.create_ticket(abgewehrt, "default")
    assert "Keine Berechtigung" in meldung_text(abgewehrt), meldung_text(abgewehrt)
    assert len(guild.ticket_kanaele()) == 1, "obwohl keine Rolle: Kanal angelegt"
    db.set_feature(11, "tickets", {**db.get_feature(11, "tickets", settings), "open_role_ids": ""},
                   1, settings, audit=False)
    bot.feature_cache.clear()

    # 4) Übernehmen und Schließen: Status, Sperre, Transkript im Log
    verwalter = FakeMember(7002, "mod", "Mod", [guild.default_role, rolle])
    guild.members[:] = [nutzer, verwalter]  # der Bot sperrt nur, wer noch da ist
    await bot.ticket_action(FakeInteraction(guild, verwalter, kanal), "claim")
    assert db.ticket_fuer_kanal(kanal.id, settings)["claimed_by"] == 7002
    kanal.nachrichten.append(FakeMessage(nutzer, "Nachricht fürs Transkript", kanal, 50))
    kanal.nachrichten.append(FakeMessage(verwalter, "Antwort des Teams", kanal, 51))
    await bot.ticket_action(FakeInteraction(guild, verwalter, kanal), "close")
    assert db.ticket_fuer_kanal(kanal.id, settings)["status"] == "closed"
    assert kanal.restrictions and kanal.restrictions[0] == nutzer.id
    assert kanal.restrictions[1]["send_messages"] is False, "Nutzer kann weiter schreiben"
    assert kanal.restrictions[1]["view_channel"] is False, "Nutzer bleibt im geschlossenen Ticket"
    assert not log.dateien, "der alte HTML-Datei-Export darf nicht mehr verwendet werden"
    schlusstag = text_aus_view(log.ansichten[-1])
    assert "Ticket geschlossen" in schlusstag, schlusstag
    assert "<@7002>" in schlusstag, schlusstag
    assert "Ticket erstellt" in text_aus_view(log.ansichten[0]), "Erstellungslog fehlt"
    await bot.ticket_action(FakeInteraction(guild, verwalter, kanal), "delete_yes")
    transcript = db.transcript_laden(kanal.id, settings)
    assert transcript and len(transcript["messages"]) >= 2, "Web-Transcript nicht gespeichert"
    assert any("Nachricht fürs Transkript" in item["content"] for item in transcript["messages"])
    assert db.ticket_fuer_kanal(kanal.id, settings)["status"] == "deleted"

    # 5) Fremder Nutzer kommt an das Ticket nicht heran
    abwehr = FakeInteraction(guild, FakeMember(7099, "anders", "Anders", [guild.default_role]), kanal)
    await bot.ticket_action(abwehr, "close")
    assert "Keine Berechtigung" in meldung_text(abwehr), meldung_text(abwehr)
    assert db.ticket_fuer_kanal(kanal.id, settings)["status"] == "deleted"

    # 6) Anti-Spam: ganze Serie löschen, Timeout, Logzeile
    bot.feature_cache.clear()  # der Bot liest Konfiguration alle drei Sekunden neu
    db.set_feature(11, "moderation", {"enabled": True, "anti_spam": True, "spam_limit": 3,
                                     "spam_timeout": True, "spam_timeout_minuten": 5,
                                     "log_channel_id": "601"}, 1, settings)
    chat = FakeChannel(guild, 800, "allgemein")
    guild._kanale[800] = chat
    spammer = FakeMember(7003, "spam", "Spam", [guild.default_role])
    for laufende in range(2):
        nachricht = FakeMessage(spammer, "hallo", chat, laufende)
        chat.nachrichten.append(nachricht)
        await bot.on_message(nachricht)
        assert not nachricht.geloescht, f"Lauf {laufende}: zu frueh geloescht"
    dritte = FakeMessage(spammer, "hallo", chat, 2)
    chat.nachrichten.append(dritte)
    await bot.on_message(dritte)
    assert all(nachricht.geloescht for nachricht in chat.nachrichten), "Serie nicht vollständig gelöscht"
    assert spammer.timeouts and spammer.timeouts[0][0] == timedelta(minutes=5), spammer.timeouts
    assert any("AutoMod: Spam" in text_aus_view(ansicht) for ansicht in log.ansichten), "Spam nicht geloggt"

    # 7) Giveaway: Abwesende gewinnen nicht, Abschluss nur einmal
    db.giveaway_anlegen(5001, 11, 807, "Preis", 2, int(time.time()) + 60, settings)
    for user_id in (7001, 7002, 9999):
        assert db.giveaway_beitreten(5001, user_id, settings) == "beitritt"
    assert db.giveaway_beitreten(5001, 7001, settings) == "bereits"
    anwesend = FakeGuild(11, "Gilde", [], [], [FakeMember(7001), FakeMember(7002)])
    giveaway_kanal = FakeChannel(anwesend, 807, "giveaways")
    anwesend._kanale[807] = giveaway_kanal
    belegt = db.giveaway_belegen(5001, settings)
    assert belegt and belegt["status"] == "ending"
    tauglich = taugliche_teilnehmer(db.giveaway_teilnehmer(5001, settings), {m.id for m in anwesend.members})
    assert tauglich == [7001, 7002], tauglich
    await bot.finish_giveaway(anwesend, dict(belegt, message_id=5001, channel_id=807, prize="Preis", winners=2))
    assert db.giveaways_fuer_gilde(11, settings, 5)[0]["status"] == "ended"
    assert db.giveaway_belegen(5001, settings) is None, "zweiter Abschluss moeglich"
    sendetext = text_aus_view(giveaway_kanal.ansichten[0])
    assert "<@7001>" in sendetext and "<@7002>" in sendetext, sendetext
    assert "9999" not in sendetext, "Abwesender als Gewinner erwaehnt"
    assert db.giveaway_beitreten(5001, 8888, settings) == "beendet", "Teilnahme nach dem Ende moeglich"

    # 8) Herzschlag: lebt, ohne den Verlaufsgraphen zu füllen
    vorher = sum(punkt["amount"] for punkt in db.feature_history(11, settings))
    await bot.heartbeat.coro(bot)  # coro ist die ungebundene Funktion
    nachher = sum(punkt["amount"] for punkt in db.feature_history(11, settings))
    assert vorher == nachher, "Herzschlag zaehlt als Konfigurationsaenderung"
    assert "zeit" in db.get_state(0, "bot_heartbeat", settings)["wert"]

    # 9) Auto-Antwort mit Abkühlzeit: dieselbe Antwort nicht zweimal
    bot.feature_cache.clear()
    db.set_feature(11, "automation", {"enabled": True}, 1, settings)
    automation_store.save_response(settings, 11, {
        "trigger": "danke", "response": "Gerne!", "cooldown_seconds": 60,
        "enabled": True, "exact": False,
    }, 1)
    dialog = FakeChannel(guild, 805, "plauder")

    async def fake_layout(channel, titel, beschreibung, **kwargs):
        return await channel.send(view=layout(titel, beschreibung, **{k: v for k, v in kwargs.items() if k != "color"}))

    bot.send_layout = fake_layout
    gast = FakeMember(7010, "gast", "Gast", [guild.default_role])
    gast.guild = guild
    for index in range(2):
        await bot.on_message(FakeMessage(gast, "danke dir", dialog, 60 + index))
    assert len(dialog.ansichten) == 1, f"Auto-Antwort dupliziert: {len(dialog.ansichten)}"

    bot.feature_cache.clear()
    # 10) Rollenknopf: vergeben, und ablehnen wenn die Rolle zu hoch sitzt
    rollen_kanal = FakeChannel(guild, 806, "rollen")
    wechsel = FakeMember(7011, "gast2", "Gast2", [guild.default_role])
    wechsel.guild = guild
    await bot.toggle_role(FakeInteraction(guild, wechsel, rollen_kanal), 40)
    assert wechsel.added and wechsel.added[0].id == 40, "Rolle nicht vergeben"
    await wechsel.add_roles(rolle)  # danach besitzt er sie -> entfernen
    await bot.toggle_role(FakeInteraction(guild, wechsel, rollen_kanal), 40)
    assert wechsel.removed and wechsel.removed[0].id == 40, "Rolle nicht entfernt"
    ueberhoch = FakeInteraction(guild, wechsel, rollen_kanal)
    await bot.toggle_role(ueberhoch, 42)   # Rolle steht hoeher als der Bot
    assert "nicht verfügbar" in meldung_text(ueberhoch), meldung_text(ueberhoch)
    verschwunden = FakeInteraction(guild, wechsel, rollen_kanal)
    await bot.toggle_role(verschwunden, 41)  # Rolle gibt es nicht mehr
    assert "Rolle fehlt" in meldung_text(verschwunden), meldung_text(verschwunden)

    print("ok   Botlauf: Modal vor defer, Tickettext, Slowmode, Transkript, Spam, Giveaway, Herzschlag")


if __name__ == "__main__":
    asyncio.run(main())
