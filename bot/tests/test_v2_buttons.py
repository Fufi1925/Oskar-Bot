#!/usr/bin/env python3
"""
Buttons that still hang below a message instead of sitting in a card.

A plain discord.ui.View puts its components underneath the message; a
LayoutView puts them inside the container with the text. After the embed
conversion the plain Views were the only thing left with the old look.

This file does two things:

  * counts what is left, so the number cannot quietly grow again
  * pins the two traps found while converting, both of which produce a
    message that looks fine in the code and is broken in Discord

Run:  python3 tests/test_v2_buttons.py
"""

import ast
import os
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


# ── resolving what is and is not a LayoutView ───────────────────────

FILES: dict[str, ast.AST] = {}


def load():
    for root, dirs, names in os.walk(BOT):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "tests"}]
        for name in names:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                try:
                    FILES[path] = ast.parse(
                        open(path, encoding="utf-8", errors="replace").read())
                except SyntaxError:
                    pass


def module_path(mod):
    candidate = os.path.join(BOT, mod.replace(".", os.sep) + ".py")
    return candidate if candidate in FILES else None


def classes_in(path):
    return {n.name: [ast.unparse(b).split(".")[-1] for b in n.bases]
            for n in ast.walk(FILES[path]) if isinstance(n, ast.ClassDef)}


def imports_in(path):
    out = {}
    for n in ast.walk(FILES[path]):
        if isinstance(n, ast.ImportFrom) and n.module:
            src = module_path(n.module)
            if src:
                for alias in n.names:
                    out[alias.asname or alias.name] = (src, alias.name)
    return out


def is_v2(path, name, seen=None):
    """
    Resolved per file, following imports.

    Doing this by bare class name across the whole repo does not work:
    two files each define an AuthorOnlyView, one a plain View and one
    not, and a global lookup reported five bugs that did not exist.
    """
    seen = seen or set()
    if (path, name) in seen:
        return False
    seen.add((path, name))
    if name == "LayoutView":
        return True
    for base in classes_in(path).get(name, []):
        if base == "LayoutView" or is_v2(path, base, seen):
            return True
        imported = imports_in(path).get(base)
        if imported and is_v2(imported[0], imported[1], seen):
            return True
    imported = imports_in(path).get(name)
    return bool(imported and is_v2(imported[0], imported[1], seen))


def is_plain_view(path, name, seen=None):
    if is_v2(path, name):
        return False
    seen = seen or set()
    if (path, name) in seen:
        return False
    seen.add((path, name))
    if name == "View":
        return True
    for base in classes_in(path).get(name, []):
        if base == "View" or is_plain_view(path, base, seen):
            return True
        imported = imports_in(path).get(base)
        if imported and is_plain_view(imported[0], imported[1], seen):
            return True
    imported = imports_in(path).get(name)
    return bool(imported and is_plain_view(imported[0], imported[1], seen))


SENDS = {"send", "reply", "send_message", "edit_message", "edit",
         "respond", "followup"}


def scope_assignments(scope):
    out = {}
    for n in ast.walk(scope):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) \
                and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            out[n.targets[0].id] = ast.unparse(n.value.func).split(".")[-1]
    return out


def test_no_plain_views_sent():
    print("\nPlain Views being sent")
    offenders = []

    for path, tree in FILES.items():
        for scope in [n for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                        ast.Module, ast.ClassDef))]:
            assigns = scope_assignments(scope)
            for node in ast.walk(scope):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in SENDS:
                    continue
                kw = {k.arg: k.value for k in node.keywords if k.arg}
                view = kw.get("view")
                if view is None:
                    continue
                if isinstance(view, ast.Constant) and view.value is None:
                    continue

                if isinstance(view, ast.Call):
                    name = ast.unparse(view.func).split(".")[-1]
                elif isinstance(view, ast.Name):
                    name = assigns.get(view.id)
                else:
                    continue
                if not name or name in ("from_embed", "from_embeds", "from_view"):
                    continue
                if is_plain_view(path, name):
                    offenders.append(
                        f"{os.path.relpath(path, BOT)}:{node.lineno} {name}")

    check("no plain View is sent directly", not offenders,
          f"{len(offenders)}: {offenders[:4]}")


def test_from_view_moves_components():
    print("\nfrom_view")
    from discord.ui import View, Button
    from utils.panels import from_view
    import discord

    view = View(timeout=42)
    view.add_item(Button(label="A_TOKEN"))
    view.add_item(Button(label="B_TOKEN"))

    panel = from_view(view, "TEXT_TOKEN")
    labels, texts = [], []

    def walk(item):
        kind = type(item).__name__
        if kind == "Button":
            labels.append(item.label)
        elif kind == "TextDisplay":
            texts.append(str(item.content))
        for child in getattr(item, "children", []) or []:
            walk(child)

    for child in panel.children:
        walk(child)

    check("it is a LayoutView", isinstance(panel, discord.ui.LayoutView))
    check("the text carries over", "TEXT_TOKEN" in "\n".join(texts))
    check("both buttons carry over",
          labels == ["A_TOKEN", "B_TOKEN"], str(labels))
    check("the timeout carries over", panel.timeout == 42)
    # A component belongs to one view at a time.
    check("the old view is emptied", len(view.children) == 0)


def test_reused_views_are_not_wrapped():
    """
    from_view() moves the components out of the view it is handed.

    That is fine for a view sent once. It is a bug for a view that is
    sent and then edited later with `view=self` -- the second send
    arrives with no buttons at all. The calculator does exactly that on
    every keypress, and wrapping it left it keyless after the first one.
    """
    print("\nViews that are sent more than once")

    for path, tree in FILES.items():
        source = open(path, encoding="utf-8").read()
        if "from_view(" not in source:
            continue
        for scope in [n for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            handed = set()
            for node in ast.walk(scope):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id == "from_view" and node.args \
                        and isinstance(node.args[0], ast.Name):
                    handed.add(node.args[0].id)
            if not handed:
                continue
            body = ast.unparse(scope)
            for var in handed:
                check(f"{os.path.relpath(path, BOT)}: {var} is not kept after wrapping",
                      f"{var}.message" not in body,
                      "the view is stored and edited later, so it would "
                      "arrive with no buttons")


def test_calculator_is_v2():
    """
    The calculator: 16 keys, and it redraws on every press.

    A LayoutView ignores @button decorators -- the class comes out with
    zero children -- so the keys had to move into ActionRow subclasses.
    Getting that wrong loses every key silently.
    """
    print("\nThe calculator")
    import asyncio
    import discord
    from cogs.commands.calc import CalculatorView

    class Author:
        display_name = "Tester"

    author = Author()
    view = CalculatorView(author)

    def collect(v):
        labels, texts = [], []

        def walk(item):
            kind = type(item).__name__
            if kind == "Button":
                labels.append(item.label)
            elif kind == "TextDisplay":
                texts.append(str(item.content))
            for child in getattr(item, "children", []) or []:
                walk(child)
        for child in v.children:
            walk(child)
        return labels, texts

    labels, texts = collect(view)
    check("it is a LayoutView", isinstance(view, discord.ui.LayoutView))
    check("all sixteen keys are there", len(labels) == 16, f"got {len(labels)}")
    for key in ("1", "0", "+", "=", "Clear"):
        check(f"the {key!r} key exists", key in labels)
    check("the display is inside the panel",
          any("Calculator" in t for t in texts),
          "the number would have to be sent as message content instead")

    # The redraw is the part that breaks quietly.
    class FakeResponse:
        @staticmethod
        async def edit_message(**kwargs):
            pass

    class FakeInteraction:
        user = author
        response = FakeResponse()
        message = None

    asyncio.run(view.update_value(FakeInteraction(), "7"))
    labels, texts = collect(view)
    check("the keys survive a keypress", len(labels) == 16, f"got {len(labels)}")
    check("the display shows the digit",
          any("7" in t for t in texts), str(texts[:1]))
    check("and the value is stored", view.value == "7", view.value)


def test_components_are_inside_the_container():
    """
    A LayoutView will happily take an ActionRow at the top level.

    It is valid, it compiles, nothing warns -- and it renders *below*
    the card, which is the exact pre-V2 look this whole conversion was
    meant to remove. The J2C panel did this with all twelve of its
    buttons: it was a LayoutView, so every scan called it converted,
    while the buttons sat outside the box the whole time.

    Components belong in a Container. Only a Container.
    """
    print("\nComponents sit inside the container")

    ROWISH = {"ActionRow", "Button", "Select", "UserSelect", "RoleSelect",
              "ChannelSelect", "MentionableSelect", "UserSelectDropdown"}
    V2BASES = {"LayoutView", "CV2", "CV2Embed", "Panel", "StatusCard"}

    def is_v2_class(cls, known):
        bases = [ast.unparse(b).split(".")[-1] for b in cls.bases]
        return any(b in V2BASES or b in known for b in bases)

    outside = []
    checked = 0

    for path, tree in FILES.items():
        # Local subclasses count too, so a two-step chain is seen.
        known = set()
        for _ in range(3):
            for cls in ast.walk(tree):
                if isinstance(cls, ast.ClassDef) and is_v2_class(cls, known):
                    known.add(cls.name)

        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if not is_v2_class(cls, known):
                continue
            checked += 1
            for node in ast.walk(cls):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "add_item":
                    continue
                if ast.unparse(node.func.value) != "self":
                    continue
                if not node.args:
                    continue
                head = ast.unparse(node.args[0]).split("(")[0].split(".")[-1].strip()
                if head in ROWISH:
                    outside.append(
                        f"{os.path.relpath(path, BOT)}:{node.lineno} "
                        f"{cls.name} -> {head}")

    print(f"\n  ({checked} V2 classes checked)")
    check("nothing is added straight to the view", not outside,
          f"{len(outside)} would render below the card: {outside[:3]}")


def test_j2c_panel():
    print("\nThe Join-to-Create panel")
    from cogs.commands.j2c import ControlPanelView

    class Guild:
        def get_channel(self, _id):
            return None

    class Cog:
        private_channels: dict = {}

    view = ControlPanelView(Cog(), Guild())

    kinds = [type(child).__name__ for child in view.children]
    check("the view holds only a container", kinds == ["Container"], str(kinds))

    buttons = []

    def walk(item):
        if type(item).__name__ == "Button":
            buttons.append(item)
        for child in getattr(item, "children", []) or []:
            walk(child)

    for child in view.children[0].children:
        walk(child)

    check("all twelve buttons are in it", len(buttons) == 12, f"got {len(buttons)}")
    # Every one of these exists in the app; a platform emoji here is
    # drawn differently by every operating system.
    platform = [b.label for b in buttons if not str(b.emoji).startswith("<")]
    check("every button uses a custom emoji", not platform, str(platform))
    check("the labels are unchanged",
          {b.label for b in buttons} == {
              "LIMIT", "PRIVACY", "THREAD", "UNTRUST", "INVITE", "KICK",
              "REGION", "UNBLOCK", "CLAIM", "TRANSFER", "DELETE", "BLOCK"},
          str(sorted(b.label for b in buttons)))
    # custom_id is what keeps a persistent view working across restarts.
    check("the custom ids survived",
          all(b.custom_id and b.custom_id.startswith("j2c:") for b in buttons),
          "a persistent panel stops responding after a restart")


def test_no_platform_emoji_on_buttons():
    """
    The app owns 142 emojis. A button reaching for the platform's ✅ or
    🔒 is drawn differently on Windows, Android and iOS, and looks
    nothing like the rest of the bot.
    """
    print("\nCustom emoji on every button")
    offenders = []

    for path, tree in FILES.items():
        for node in ast.walk(tree):
            calls = []
            if isinstance(node, ast.Call) and \
                    ast.unparse(node.func).split(".")[-1] == "Button":
                calls.append(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls += [d for d in node.decorator_list
                          if isinstance(d, ast.Call)
                          and ast.unparse(d.func).split(".")[-1] == "button"]
            for call in calls:
                for keyword in call.keywords:
                    if keyword.arg != "emoji":
                        continue
                    value = keyword.value
                    if isinstance(value, ast.Constant) and \
                            isinstance(value.value, str) and \
                            not value.value.startswith("<"):
                        label = next(
                            (ast.unparse(k.value).strip("'\"")
                             for k in call.keywords if k.arg == "label"), "?")
                        offenders.append(
                            f"{os.path.relpath(path, BOT)}:{call.lineno} "
                            f"{label} {value.value}")

    check("no button carries a platform emoji", not offenders,
          f"{len(offenders)}: {offenders[:4]}")


def main():
    load()
    test_no_plain_views_sent()
    test_from_view_moves_components()
    test_reused_views_are_not_wrapped()
    test_calculator_is_v2()
    test_components_are_inside_the_container()
    test_j2c_panel()
    test_no_platform_emoji_on_buttons()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
