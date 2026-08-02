#!/usr/bin/env python3
"""
Converting an embed to Components V2 must not lose a single word.

This is the safety net for the bulk conversion. An embed has nine places
text can hide -- title, url, description, author name, author url, field
names, field values, footer, timestamp -- plus two images. The first
version of from_embed() kept four of them and silently dropped the rest.

Rather than list what to check, this generates embeds, converts them,
and asserts every string that went in comes out. A part that is added to
Discord later and forgotten here will not be caught, but nothing
currently expressible in an embed can go missing.

Run:  python3 tests/test_embed_lossless.py
"""

import datetime
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

import discord  # noqa: E402
from utils.panels import from_embed  # noqa: E402

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def harvest(panel):
    """All text, thumbnails and images anywhere in a panel."""
    texts: list[str] = []
    thumbs: list[object] = []
    galleries: list[object] = []

    def walk(item):
        kind = type(item).__name__
        if kind == "TextDisplay":
            texts.append(str(item.content))
        elif kind == "Thumbnail":
            thumbs.append(item)
        elif kind == "MediaGallery":
            galleries.append(item)
        for child in getattr(item, "children", []) or []:
            walk(child)
        accessory = getattr(item, "accessory", None)
        if accessory is not None:
            walk(accessory)

    for child in panel.children:
        walk(child)
    return "\n".join(texts), thumbs, galleries


def test_every_part_survives():
    print("\nEvery part of a full embed")
    stamp = datetime.datetime(2026, 8, 2, 12, 0, tzinfo=datetime.timezone.utc)
    embed = discord.Embed(
        title="TITLE_TOKEN",
        description="DESCRIPTION_TOKEN",
        url="https://example.com/TITLEURL_TOKEN",
        color=0xFF0000,
        timestamp=stamp,
    )
    embed.set_author(name="AUTHOR_TOKEN", url="https://example.com/AUTHORURL_TOKEN")
    embed.add_field(name="FIELDNAME_TOKEN", value="FIELDVALUE_TOKEN", inline=False)
    embed.set_thumbnail(url="https://example.com/THUMB_TOKEN.png")
    embed.set_image(url="https://example.com/IMAGE_TOKEN.png")
    embed.set_footer(text="FOOTER_TOKEN")

    text, thumbs, galleries = harvest(from_embed(embed))

    for token in ("TITLE_TOKEN", "TITLEURL_TOKEN", "DESCRIPTION_TOKEN",
                  "AUTHOR_TOKEN", "AUTHORURL_TOKEN", "FIELDNAME_TOKEN",
                  "FIELDVALUE_TOKEN", "FOOTER_TOKEN"):
        check(f"{token.split('_')[0].lower()} survives", token in text)

    # A timestamp is not a string; it has to arrive as a Discord
    # timestamp tag or it is gone.
    check("timestamp survives", f"<t:{int(stamp.timestamp())}" in text,
          "the embed's date is not shown anywhere")
    check("thumbnail survives", bool(thumbs),
          "81 embeds set one and it was being dropped")
    check("image survives", bool(galleries))


def test_every_combination():
    """
    Not just the full embed: every subset of the optional parts.

    A part can be lost by an ordering bug that only shows when something
    else is absent -- the thumbnail attaches to the first text block, so
    an embed with a thumbnail and no text is its own case.
    """
    print("\nEvery combination of optional parts")
    parts = ("title", "description", "author", "field", "footer",
             "thumb", "image", "stamp")
    stamp = datetime.datetime(2026, 8, 2, 12, 0, tzinfo=datetime.timezone.utc)

    lost: list[str] = []
    crashed: list[str] = []
    total = 0

    for size in range(len(parts) + 1):
        for combo in itertools.combinations(parts, size):
            total += 1
            embed = discord.Embed()
            expect: list[str] = []

            if "title" in combo:
                embed.title = "T_TOKEN"
                expect.append("T_TOKEN")
            if "description" in combo:
                embed.description = "D_TOKEN"
                expect.append("D_TOKEN")
            if "author" in combo:
                embed.set_author(name="A_TOKEN")
                expect.append("A_TOKEN")
            if "field" in combo:
                embed.add_field(name="FN_TOKEN", value="FV_TOKEN")
                expect += ["FN_TOKEN", "FV_TOKEN"]
            if "footer" in combo:
                embed.set_footer(text="FT_TOKEN")
                expect.append("FT_TOKEN")
            if "thumb" in combo:
                embed.set_thumbnail(url="https://example.com/th.png")
            if "image" in combo:
                embed.set_image(url="https://example.com/im.png")
            if "stamp" in combo:
                embed.timestamp = stamp

            try:
                text, thumbs, galleries = harvest(from_embed(embed))
            except Exception as exc:
                crashed.append(f"{combo}: {type(exc).__name__}")
                continue

            for token in expect:
                if token not in text:
                    lost.append(f"{token} missing from {combo}")
            if "stamp" in combo and "<t:" not in text:
                lost.append(f"timestamp missing from {combo}")
            if "thumb" in combo and not (thumbs or galleries):
                lost.append(f"thumbnail missing from {combo}")
            if "image" in combo and not galleries:
                lost.append(f"image missing from {combo}")

    print(f"\n  ({total} combinations checked)")
    check("nothing crashes", not crashed, f"{crashed[:3]}")
    check("nothing is lost", not lost, f"{len(lost)} losses, e.g. {lost[:3]}")


def test_inline_fields_stay_together():
    print("\nInline fields")
    embed = discord.Embed(title="t")
    embed.add_field(name="A", value="1", inline=True)
    embed.add_field(name="B", value="2", inline=True)
    embed.add_field(name="C", value="3", inline=False)

    text, _, _ = harvest(from_embed(embed))
    # Inline fields sat side by side; V2 has no columns, so they are
    # joined rather than becoming a stack of tiny separated sections.
    check("inline fields share a block",
          "**A**\n1\n\n**B**\n2" in text,
          "each inline field became its own section")
    check("a non-inline field stays separate", "**C**\n3" in text)


def test_awkward_content():
    print("\nAwkward content")

    # Markdown in a field value must not be mangled by the wrapper.
    embed = discord.Embed(description="**bold** `code` [link](https://x.com)")
    text, _, _ = harvest(from_embed(embed))
    check("markdown is passed through",
          "**bold**" in text and "[link](https://x.com)" in text)

    # A completely empty embed must not raise.
    try:
        from_embed(discord.Embed())
        check("an empty embed is fine", True)
    except Exception as exc:
        check("an empty embed is fine", False, f"{type(exc).__name__}: {exc}")

    # embed=None has to come back as None, not raise. Several callers
    # build an optional embed -- a greeting can be plain text -- and
    # passed None straight to send(), which discord.py accepts. Wrapping
    # that in from_embed() turned a working path into AttributeError,
    # and the welcome test caught it only by accident.
    try:
        result = from_embed(None)
        check("embed=None gives back None", result is None, f"got {result!r}")
    except Exception as exc:
        check("embed=None gives back None", False,
              f"raised {type(exc).__name__}: {exc}")
    try:
        check("and with a view too", from_embed(None, discord.ui.View()) is None)
    except Exception as exc:
        check("and with a view too", False, f"raised {type(exc).__name__}")

    # Discord's own limits: 256-char title, 4096 description, 1024 field.
    embed = discord.Embed(title="x" * 256, description="y" * 4096)
    embed.add_field(name="z" * 256, value="w" * 1024)
    try:
        text, _, _ = harvest(from_embed(embed))
        check("maximum-length content survives",
              "x" * 256 in text and "y" * 4096 in text and "w" * 1024 in text)
    except Exception as exc:
        check("maximum-length content survives", False,
              f"{type(exc).__name__}: {exc}")

    # A newline-heavy value must not lose its shape.
    embed = discord.Embed(description="line1\nline2\n\nline4")
    text, _, _ = harvest(from_embed(embed))
    check("line breaks are preserved", "line1\nline2\n\nline4" in text)


def test_colour_and_buttons():
    print("\nColour and buttons")
    from discord.ui import View, Button

    embed = discord.Embed(title="t", color=0x00FF00)
    view = View()
    view.add_item(Button(label="B_TOKEN"))

    panel = from_embed(embed, view)
    accent = panel.children[0].accent_colour
    value = accent if isinstance(accent, int) else getattr(accent, "value", None)
    check("the colour carries over", value == 0x00FF00, f"got {value}")

    text, _, _ = harvest(panel)
    labels = []

    def walk(item):
        if type(item).__name__ == "Button":
            labels.append(item.label)
        for child in getattr(item, "children", []) or []:
            walk(child)

    for child in panel.children:
        walk(child)
    check("the button carries over", "B_TOKEN" in labels)
    check("the old view is emptied", len(view.children) == 0,
          "a component belongs to one view at a time")


def main():
    test_every_part_survives()
    test_every_combination()
    test_inline_fields_stay_together()
    test_awkward_content()
    test_colour_and_buttons()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
