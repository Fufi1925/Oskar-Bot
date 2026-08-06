#!/usr/bin/env python3
"""
Das aufgeraeumte /-Menue.

Ausgangslage: 73 Namen im ``/``-Menue, 129 aufrufbare Befehle. Discord
erlaubt 100 globale Befehle -- viel Luft war nicht mehr, und die
Einrichtungs-Befehle deckten die eigentliche Bedienung zu.

Die Einrichtung ist deshalb aus dem Menue genommen
(``with_app_command=False``): automod, log, greet, verification, media,
setup (customrole), nightmode, filter, createrr, dmrr, extraowner und
die vier whitelist-Befehle.

Die Vorgabe war ausdruecklich: **jeder Befehl bleibt als Prefix
erhalten**. Nur der Weg ueber ``/`` faellt weg.

Was hier geprueft wird:

  1. Die Dekoratoren stehen wirklich an den richtigen Stellen -- und
     an keiner falschen.
  2. ``utils/command_surface.py`` erkennt korrekt, wo ein Befehl lebt.
     Der naheliegende Weg ueber ``app_command is not None`` funktioniert
     NICHT: discord.py setzt das Feld auf ``MISSING``, nicht auf
     ``None``. Die erste Fassung meldete deshalb fuer jeden Befehl
     "hat Slash".
  3. Jeder aus dem Menue genommene Befehl hat einen Eintrag in der
     Dashboard-Zuordnung -- sonst schweigt die Hilfe dazu.
  4. ``>help`` nennt beide Zahlen getrennt und verlinkt das Dashboard.

Run:  python3 tests/test_slash_cleanup.py
"""

import ast
import asyncio
import os
import re
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

os.environ.setdefault("TOKEN", "x")
warnings.filterwarnings("ignore")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def source(*parts) -> str:
    return open(os.path.join(BOT, *parts), encoding="utf-8").read()


def strip_python(src: str) -> str:
    """Kommentare und Docstrings raus -- sonst treffen die Suchen sie."""

    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    tree = ast.parse(src)
    lines = src.split("\n")
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)
        ):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        first = node.body[0]
        for index in range(first.lineno - 1, first.end_lineno):
            lines[index] = ""
    return "\n".join(lines)


# Was aus dem /-Menue verschwinden sollte.
REMOVED = {
    "automod", "log", "greet", "verification", "media", "setup",
    "nightmode", "filter", "createrr", "dmrr", "extraowner",
    "whitelist", "whitelisted", "whitelistreset", "unwhitelist",
}

# Was ausdruecklich bleiben muss -- Bedienung, nicht Einrichtung.
KEPT = {
    "ban", "kick", "mute", "warn", "lock", "unlock", "nuke", "clone",
    "userinfo", "serverinfo", "avatar", "ping", "list", "stats",
    "gstart", "gend", "greroll", "glist", "ticket",
    "wordle", "chess", "rps", "afk", "antinuke", "embed", "poll",
    "rank", "leaderboard", "timer",
    # Ohne Dashboard-Seite: waere sonst gar nicht mehr im Menue.
    "minecraft",
}


def command_decorator(node):
    """(Dekorator, Aufruf, Name) des Befehls-Dekorators, oder (None, ...)."""

    for deco in node.decorator_list:
        call = deco if isinstance(deco, ast.Call) else None
        target = call.func if call else deco
        text = ast.unparse(target)

        if not (text.endswith("hybrid_group") or text.endswith("hybrid_command")):
            continue

        name = node.name
        if call:
            for keyword in call.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    name = keyword.value.value
            if call.args and isinstance(call.args[0], ast.Constant):
                name = call.args[0].value
        return deco, call, name
    return None, None, None


def collect_decorators() -> dict[str, bool]:
    """Name -> steht `with_app_command=False` daran?

    Nur die obersten Befehle: Unterbefehle erben die Entscheidung.
    """

    found: dict[str, bool] = {}
    for folder, dirs, files in os.walk(os.path.join(BOT, "cogs")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for filename in sorted(files):
            if not filename.endswith(".py"):
                continue
            path = os.path.join(folder, filename)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                deco, _call, name = command_decorator(node)
                if deco is None:
                    continue
                text = ast.unparse(deco)
                found[name] = "with_app_command=False" in text
    return found


# --------------------------------------------------------------------- #
# 1. Die Dekoratoren
# --------------------------------------------------------------------- #


def test_the_setup_commands_left_the_slash_menu():
    print("\nDie Einrichtungs-Befehle sind aus dem /-Menue")

    found = collect_decorators()

    missing = sorted(n for n in REMOVED if n not in found)
    check("alle Zielbefehle sind auffindbar", not missing, f"fehlen: {missing}")

    not_disabled = sorted(n for n in REMOVED if found.get(n) is False)
    check("und alle tragen with_app_command=False",
          not not_disabled,
          f"noch im Menue: {not_disabled}")


def test_the_everyday_commands_stayed():
    """Ein zu breiter Suchlauf haette auch die Bedienung erwischt."""

    print("\nDie taeglichen Befehle sind noch im /-Menue")

    found = collect_decorators()

    wrongly_removed = sorted(
        name for name in KEPT if found.get(name) is True
    )
    check("nichts aus der Bedienung wurde entfernt",
          not wrongly_removed,
          f"faelschlich entfernt: {wrongly_removed}")


def test_nothing_else_was_touched():
    """Genau fuenfzehn Befehle -- nicht mehr."""

    print("\nGenau die geplanten fuenfzehn")

    found = collect_decorators()
    disabled = {name for name, off in found.items() if off}

    extra = sorted(disabled - REMOVED)
    check("keine zusaetzlichen Befehle abgeschaltet",
          not extra,
          f"zusaetzlich: {extra}")
    check("es sind genau fuenfzehn",
          len(disabled) == 15,
          f"{len(disabled)}: {sorted(disabled)}")


# --------------------------------------------------------------------- #
# 2. command_surface erkennt die Lage
# --------------------------------------------------------------------- #


def test_the_surface_helper_is_honest():
    """`app_command is not None` haette hier immer True gesagt."""

    print("\ncommand_surface erkennt, wo ein Befehl lebt")

    import discord
    from discord.ext import commands

    from utils import command_surface as surface

    class Sample(commands.Cog):
        @commands.hybrid_group(name="automod", with_app_command=False)
        async def automod(self, ctx):
            pass

        @automod.command(name="enable")
        async def enable(self, ctx):
            pass

        @commands.hybrid_command(name="ban")
        async def ban(self, ctx):
            pass

        @commands.command(name="prefixonly")
        async def prefixonly(self, ctx):
            pass

    async def build():
        bot = commands.Bot(command_prefix=">", intents=discord.Intents.none())
        await bot.add_cog(Sample())
        return bot

    bot = asyncio.run(build())

    cases = [
        ("automod", False),
        # Der Unterbefehl erbt: sein eigenes Flag steht auf True.
        ("automod enable", False),
        ("ban", True),
        ("prefixonly", False),
    ]
    for name, expected in cases:
        command = bot.get_command(name)
        check(f"{name}: has_slash = {expected}",
              surface.has_slash(command) is expected,
              f"gemeldet: {surface.has_slash(command)}")

    # Und die Gegenprobe am echten Baum.
    tree_names = {c.name for c in bot.tree.get_commands()}
    check("der Baum enthaelt nur 'ban'",
          tree_names == {"ban"},
          str(tree_names))

    check("das Abzeichen passt",
          surface.surface_badge(bot.get_command("ban")) == "`/` + Prefix"
          and surface.surface_badge(bot.get_command("automod")) == "nur Prefix")


def test_the_hint_points_somewhere_real():
    print("\nDer Dashboard-Hinweis")

    import discord
    from discord.ext import commands

    from utils import command_surface as surface

    class Sample(commands.Cog):
        @commands.hybrid_group(name="automod", with_app_command=False)
        async def automod(self, ctx):
            pass

        @commands.hybrid_group(name="media", with_app_command=False)
        async def media(self, ctx):
            pass

        @commands.hybrid_command(name="ban")
        async def ban(self, ctx):
            pass

    async def build():
        bot = commands.Bot(command_prefix=">", intents=discord.Intents.none())
        await bot.add_cog(Sample())
        return bot

    bot = asyncio.run(build())

    hint = surface.dashboard_hint(bot.get_command("automod"), 123)
    check("automod verweist aufs Dashboard",
          "automod" in hint and "Dashboard" in hint,
          hint)

    # media hat keine Seite -- kein toter Link.
    hint = surface.dashboard_hint(bot.get_command("media"), 123)
    check("media nennt keine Seite, die es nicht gibt",
          "Dashboard" not in hint and "Prefix" in hint,
          hint)

    check("ein normaler Befehl bekommt keinen Hinweis",
          surface.dashboard_hint(bot.get_command("ban"), 123) == "")


def test_every_removed_command_is_explained():
    """Ohne Eintrag schweigt die Hilfe -- und der Nutzer sucht."""

    print("\nJeder entfernte Befehl ist erklaert")

    from utils import command_surface as surface

    covered = set(surface.DASHBOARD_TAB) | surface.NO_DASHBOARD_PAGE

    missing = sorted(REMOVED - covered)
    check("alle fuenfzehn sind zugeordnet", not missing, f"fehlen: {missing}")

    extra = sorted(covered - REMOVED)
    check("und es steht nichts Ueberfluessiges drin",
          not extra,
          f"zusaetzlich: {extra}")

    check("SETUP_COMMANDS deckt sich damit",
          surface.SETUP_COMMANDS == REMOVED,
          f"Differenz: {sorted(surface.SETUP_COMMANDS ^ REMOVED)}")


def test_the_tabs_exist_in_the_dashboard():
    """Ein Link auf eine Seite, die es nicht gibt, ist schlimmer als keiner."""

    print("\nDie verlinkten Reiter gibt es wirklich")

    from utils import command_surface as surface

    pages = os.path.join(
        os.path.dirname(BOT), "dashboard", "app", "dashboard", "guild", "[guildId]"
    )
    if not os.path.isdir(pages):
        print("  skip (dashboard liegt nicht daneben)")
        return

    existing = {
        name for name in os.listdir(pages)
        if os.path.isdir(os.path.join(pages, name))
    }

    for command, tab in sorted(surface.DASHBOARD_TAB.items()):
        check(f"{command} -> /{tab}",
              tab in existing,
              f"es gibt keinen Ordner '{tab}'")


# --------------------------------------------------------------------- #
# 3. >help
# --------------------------------------------------------------------- #


def test_help_counts_both_kinds():
    """`walk_commands()` allein kennt keine Slash-Befehle."""

    print("\n>help nennt beide Zahlen")

    src = strip_python(source("cogs", "commands", "help.py"))

    check("die Prefix-Zahl steht drin", "prefix_total" in src)
    check("und die Slash-Zahl", "slash_total" in src)
    check("sie kommt aus dem Baum",
          "tree.get_commands()" in src,
          "walk_commands() kennt nur Prefix-Befehle")
    check("beide werden angezeigt",
          "{prefix_total}" in src and "{slash_total}" in src)


def test_help_explains_where_a_command_lives():
    print("\n>help sagt, wo ein Befehl lebt")

    src = strip_python(source("cogs", "commands", "help.py"))
    tree = ast.parse(src)

    single = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "send_command_help"),
        None,
    )
    check("es gibt send_command_help", single is not None)
    if single is not None:
        body = ast.unparse(single)
        check("die Einzelansicht fragt command_surface",
              "surface.has_slash(" in body)
        check("und zeigt den Dashboard-Hinweis",
              "surface.dashboard_hint(" in body)
        check("sie nennt den Befehl auch ohne /",
              "nicht im" in body,
              "sonst haelt man ihn fuer geloescht")

    group = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "send_group_help"),
        None,
    )
    check("es gibt send_group_help", group is not None)
    if group is not None:
        body = ast.unparse(group)
        check("die Gruppenansicht ebenso",
              "surface.has_slash(" in body and "surface.dashboard_hint(" in body)


def main() -> int:
    test_the_setup_commands_left_the_slash_menu()
    test_the_everyday_commands_stayed()
    test_nothing_else_was_touched()
    test_the_surface_helper_is_honest()
    test_the_hint_points_somewhere_real()
    test_every_removed_command_is_explained()
    test_the_tabs_exist_in_the_dashboard()
    test_help_counts_both_kinds()
    test_help_explains_where_a_command_lives()

    print()
    if failures:
        print(f"{len(failures)} failures")
        for entry in failures:
            print(f"  - {entry}")
        return 1

    print("0 failures, 0 skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
