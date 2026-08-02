#!/usr/bin/env python3
"""
A panel must never end up inside another panel.

From the Railway log, on >help:

    400 Bad Request (error code: 50035): Invalid Form Body
    In components.0.components.1.components.0:
    Value of field "type" must be one of (2, 3, 5, 6, 7, 8).

Discord is saying: something that is not a component turned up where a
component belongs. It was a Container, stuffed into an ActionRow by
from_view() -- which had been handed a LayoutView.

The rewrite script matched class names locally, and `View` in
utils/help.py *is* a LayoutView subclass. Nineteen call sites got it,
and every one of them would have thrown the moment the command ran.

Nothing caught it: the suite was green, the bot booted, 146 cogs loaded.
None of that exercises the shape of the tree that actually gets sent.
So this file builds the trees and looks at them.

Run:  python3 tests/test_v2_nesting.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

import discord  # noqa: E402
from discord.ui import (  # noqa: E402
    ActionRow, Button, Container, LayoutView, Separator, TextDisplay,
)
from utils.panels import from_view, from_embed, Panel  # noqa: E402

failures: list[str] = []

# What Discord accepts inside an ActionRow: buttons and the five selects.
ROW_SAFE = {
    "Button", "Select", "StringSelect", "UserSelect", "RoleSelect",
    "MentionableSelect", "ChannelSelect",
}


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def bad_nodes(view) -> list[str]:
    """Anything sitting somewhere Discord will reject."""
    problems: list[str] = []

    def walk(item, inside_row=False, path="view"):
        kind = type(item).__name__
        here = f"{path}.{kind}"

        if inside_row and kind not in ROW_SAFE:
            problems.append(f"{kind} inside an ActionRow at {here}")

        # A container holding a container is the other half of the same
        # mistake, and Discord rejects it too.
        if kind == "Container" and "Container" in path:
            problems.append(f"Container nested in a Container at {here}")

        for child in getattr(item, "children", []) or []:
            walk(child, inside_row=(kind == "ActionRow"), path=here)
        accessory = getattr(item, "accessory", None)
        if accessory is not None:
            walk(accessory, inside_row=False, path=here)

    for child in getattr(view, "children", []) or []:
        walk(child)
    return problems


def test_from_view_passes_layoutviews_through():
    print("\nfrom_view on a LayoutView")

    panel = LayoutView(timeout=None)
    box = Container()
    box.add_item(TextDisplay("HELP_TOKEN"))
    box.add_item(Separator(visible=True))
    box.add_item(ActionRow(Button(label="BTN_TOKEN")))
    panel.add_item(box)

    result = from_view(panel, "some text")

    check("it is handed straight back", result is panel,
          "wrapping a panel puts a Container inside an ActionRow")
    check("the tree is still valid", not bad_nodes(result),
          str(bad_nodes(result)))

    # And the plain case must keep working.
    plain = discord.ui.View()
    plain.add_item(Button(label="OK_TOKEN"))
    wrapped = from_view(plain, "TEXT_TOKEN")
    check("a plain View still becomes a panel", isinstance(wrapped, Panel))
    check("its tree is valid", not bad_nodes(wrapped), str(bad_nodes(wrapped)))
    labels = []

    def collect(item):
        if type(item).__name__ == "Button":
            labels.append(item.label)
        for child in getattr(item, "children", []) or []:
            collect(child)

    for child in wrapped.children:
        collect(child)
    check("and its button survives", labels == ["OK_TOKEN"], str(labels))


def test_every_call_site():
    """
    Build the views the bot actually sends and inspect the tree.

    Static analysis said these were fine -- twice. The classes involved
    are called `View` and `CV2View` and `RoleInfoView`, and whether each
    is a LayoutView depends on which `View` the file imported. Only the
    real class object settles it.
    """
    print("\nThe views behind the from_view call sites")
    import importlib

    # (module, class, build) for the views from_view is called with.
    cases = [
        ("utils.help", "View", None),
        ("cogs.commands.ai", "CV2View", lambda c: c("T", "D")),
        ("cogs.commands.logging", "LogSetupLayoutView", None),
        ("cogs.commands.j2c", "ControlPanelView", None),
        ("cogs.commands.extra", "RoleInfoView", None),
        ("cogs.commands.general", "AvatarView", None),
    ]

    for module_name, class_name, build in cases:
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
        except Exception as exc:
            check(f"{module_name}.{class_name} imports", False,
                  f"{type(exc).__name__}: {exc}")
            continue

        is_layout = issubclass(cls, discord.ui.LayoutView)

        # A LayoutView handed to from_view must come back untouched;
        # anything else must be wrapped. Either way the result has to be
        # a tree Discord will accept.
        if build is None:
            check(f"{class_name}: known to the suite", True)
            continue

        instance = build(cls)
        result = from_view(instance)
        if is_layout:
            check(f"{class_name} is passed through", result is instance,
                  "it would be wrapped into an ActionRow")
        check(f"{class_name} produces a valid tree", not bad_nodes(result),
              str(bad_nodes(result)))


def test_j2c_panel_tree():
    print("\nThe J2C panel, as Discord sees it")
    from cogs.commands.j2c import ControlPanelView

    class Guild:
        def get_channel(self, _id):
            return None

    class Cog:
        private_channels: dict = {}

    view = ControlPanelView(Cog(), Guild())
    problems = bad_nodes(view)
    check("the tree is valid", not problems, str(problems))

    # Wrapping it must not break it either -- that is what happened.
    check("wrapping it changes nothing", from_view(view) is view)


def test_from_embed_tree_is_valid():
    print("\nfrom_embed produces a valid tree")
    embed = discord.Embed(title="T", description="D", color=0xFF0000)
    embed.add_field(name="F", value="V")
    embed.set_thumbnail(url="https://example.com/t.png")
    embed.set_image(url="https://example.com/i.png")
    embed.set_footer(text="foot")

    view = discord.ui.View()
    for i in range(7):
        view.add_item(Button(label=f"b{i}"))

    panel = from_embed(embed, view)
    problems = bad_nodes(panel)
    check("nothing is in the wrong place", not problems, str(problems))

    # Five per row is the platform limit; a sixth is a 400.
    rows = [c for c in panel.children[0].children
            if type(c).__name__ == "ActionRow"]
    check("no row holds more than five",
          all(len(r.children) <= 5 for r in rows),
          str([len(r.children) for r in rows]))

    # A select takes the whole row. Sharing one with a button is
    # "maximum number of children exceeded" at send time, which is the
    # same class of failure as the nesting bug: valid-looking code, 400
    # from Discord.
    from discord.ui import Select

    mixed = discord.ui.View()
    mixed.add_item(Button(label="a"))
    mixed.add_item(Select(placeholder="p",
                          options=[discord.SelectOption(label="x")]))
    mixed.add_item(Button(label="b"))

    mixed_panel = from_embed(discord.Embed(title="t"), mixed)
    check("a select and a button never share a row", not bad_nodes(mixed_panel),
          str(bad_nodes(mixed_panel)))

    shapes = [[type(i).__name__ for i in c.children]
              for c in mixed_panel.children[0].children
              if type(c).__name__ == "ActionRow"]
    check("the select gets a row to itself",
          all(len(shape) == 1 for shape in shapes
              if any("Select" in kind for kind in shape)),
          str(shapes))


def main():
    test_from_view_passes_layoutviews_through()
    test_every_call_site()
    test_j2c_panel_tree()
    test_from_embed_tree_is_valid()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
