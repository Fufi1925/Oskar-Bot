#!/usr/bin/env python3
"""
Eine Rechteprüfung darf beim Umbau zu Components V2 nicht verloren gehen.

Der Fund, um den es geht: `from_embed(embed, view)` verschiebt die
Knöpfe der übergebenen View in ein neues Panel. Die alte View behält
ihr `interaction_check` und wird nie gesendet — Discord ruft die
Prüfung der View auf, mit der die *Nachricht* verschickt wurde.

Ergebnis: die Ticket-Knöpfe (Claim, Lock, Close) waren durch eine
Team-Rollen-Prüfung geschützt, die nie lief. Jeder im Kanal konnte ein
fremdes Ticket schließen.

Drei Aufrufstellen waren betroffen, alle in tickets.py. Behoben wurde
es in `from_embed` selbst, denn die nächste View mit Prüfung liefe in
dieselbe Falle.

Run:  python3 tests/test_panel_permission_check.py
"""

import ast
import asyncio
import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def test_the_check_survives_the_conversion():
    """Der eigentliche Fehler: die Prüfung wurde stillschweigend fallengelassen."""

    print("\nDie Rechteprüfung überlebt den Umbau")
    import discord

    from utils.panels import from_embed

    seen: list = []

    class Guarded(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        async def interaction_check(self, interaction) -> bool:
            seen.append(interaction)
            return False

        @discord.ui.button(label="Claim", custom_id="t_claim")
        async def claim(self, interaction, button):
            pass

        @discord.ui.button(label="Close", custom_id="t_close")
        async def close(self, interaction, button):
            pass

    source = Guarded()
    check("die View hat zwei Knöpfe", len(source.children) == 2)

    panel = from_embed(discord.Embed(title="Ticket", description="x"), source)

    # Die Knöpfe wandern -- das ist so gewollt, eine Komponente gehört
    # zu genau einer View.
    check("die Knöpfe sind umgezogen", len(source.children) == 0)

    # Aber die Prüfung muss mitkommen.
    base = discord.ui.View.interaction_check
    own = getattr(panel, "interaction_check", None)
    check("das Panel hat eine eigene Prüfung",
          own is not None and getattr(own, "__func__", own) is not base)

    allowed = asyncio.run(panel.interaction_check("interaktion"))
    check("sie wird wirklich aufgerufen", len(seen) == 1, f"{len(seen)}x")
    check("und ihr Nein gilt", allowed is False, str(allowed))
    check("die Interaktion kommt unverändert an",
          seen and seen[0] == "interaktion", str(seen))


def test_a_view_without_a_check_stays_open():
    """Gegenprobe: es wird nichts erfunden, was nicht da war.

    Ohne diese Prüfung wäre der Test oben auch grün, wenn from_embed
    jedem Panel blind eine Ablehnung verpasste -- und dann ginge kein
    einziger Knopf im ganzen Bot mehr.
    """

    print("\nOhne Prüfung bleibt es offen")
    import discord

    from utils.panels import from_embed

    class Plain(discord.ui.View):
        @discord.ui.button(label="Weiter", custom_id="x")
        async def go(self, interaction, button):
            pass

    panel = from_embed(discord.Embed(title="T", description="x"), Plain())
    base = discord.ui.View.interaction_check
    own = getattr(panel, "interaction_check", None)
    check("keine Prüfung erfunden",
          own is None or getattr(own, "__func__", own) is base,
          "eine erfundene Ablehnung würde jeden Knopf blockieren")

    # Und ohne View überhaupt darf nichts krachen.
    bare = from_embed(discord.Embed(title="T", description="x"))
    check("ohne View kein Absturz", bare is not None)


def test_the_check_keeps_its_own_state():
    """Sie liest self.cog und self.cat_id -- das muss die alte View bleiben."""

    print("\nDie Prüfung behält ihren Zustand")
    import discord

    from utils.panels import from_embed

    class Stateful(discord.ui.View):
        def __init__(self, category_id):
            super().__init__(timeout=None)
            self.category_id = category_id

        async def interaction_check(self, interaction) -> bool:
            # Genau das Muster aus tickets.py: die Prüfung greift auf
            # Felder der Instanz zu. An das Panel gebunden gäbe es hier
            # AttributeError -- und zwar erst, wenn jemand klickt.
            return self.category_id == 42

        @discord.ui.button(label="A", custom_id="a")
        async def a(self, interaction, button):
            pass

    panel = from_embed(discord.Embed(title="T", description="x"), Stateful(42))
    check("die Prüfung findet ihre Daten",
          asyncio.run(panel.interaction_check(None)) is True)

    other = from_embed(discord.Embed(title="T", description="x"), Stateful(7))
    check("und zwar die der eigenen View",
          asyncio.run(other.interaction_check(None)) is False,
          "zwei Panels teilen sich sonst einen Zustand")


def test_panels_do_not_leak_into_each_other():
    """Die Prüfung darf nicht an der Klasse hängen.

    Panel ist gemeinsam genutzt. Ein Klassenattribut würde die Prüfung
    des einen Tickets in jedes danach gebaute Panel tragen -- und dann
    entscheidet Ticket A darüber, wer in Ticket B klicken darf.
    """

    print("\nEin Panel färbt nicht auf das nächste ab")
    import discord

    from utils.panels import Panel, from_embed

    class Guarded(discord.ui.View):
        async def interaction_check(self, interaction) -> bool:
            return False

        @discord.ui.button(label="A", custom_id="a")
        async def a(self, interaction, button):
            pass

    from_embed(discord.Embed(title="T", description="x"), Guarded())

    base = discord.ui.View.interaction_check
    check("die Panel-Klasse bleibt unberührt",
          Panel.interaction_check is base,
          "die Prüfung hängt an der Klasse statt an der Instanz")

    fresh = Panel("Neu", "ohne Prüfung")
    own = getattr(fresh, "interaction_check", None)
    check("ein neues Panel ist frei",
          getattr(own, "__func__", own) is base,
          "es hat die Prüfung des vorigen Tickets geerbt")


def test_every_guarded_view_goes_through_the_fix():
    """Welche Aufrufstellen sind betroffen -- und sind es noch dieselben?

    Kommt eine neue dazu, ist sie durch den Fix in from_embed gedeckt.
    Diese Prüfung dokumentiert nur, wo es überhaupt zählt, damit der
    Umfang nicht unbemerkt wächst.
    """

    print("\nDie betroffenen Aufrufstellen")

    found = []
    for path in pathlib.Path(os.path.join(BOT, "cogs")).rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        guarded = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "interaction_check"
                for item in node.body
            )
        }
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "from_embed"
                and len(node.args) >= 2
            ):
                continue
            name = getattr(getattr(node.args[1], "func", None), "id", "")
            if name in guarded:
                found.append(f"{path.name}:{node.lineno} {name}")

    check("es gibt betroffene Stellen", bool(found),
          "findet die Suche noch etwas? Sonst prüft sie nichts")
    print(f"       {len(found)} Stellen: {found}")

    # Alle in tickets.py -- ändert sich das, lohnt ein zweiter Blick.
    outside = [entry for entry in found if not entry.startswith("ticket.py")]
    check("alle liegen in ticket.py", not outside, str(outside))


def main():
    test_the_check_survives_the_conversion()
    test_a_view_without_a_check_stays_open()
    test_the_check_keeps_its_own_state()
    test_panels_do_not_leak_into_each_other()
    test_every_guarded_view_goes_through_the_fix()

    print()
    if failures:
        print(f"FAILED {len(failures)}")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("Alle Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
