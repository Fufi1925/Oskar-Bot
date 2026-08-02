#!/usr/bin/env python3
"""
Components V2 conversion, and custom emojis on the buttons.

Three things this pins down:

  * **An embed is never sent together with a V2 view.** Discord rejects
    the message outright -- the two are mutually exclusive. Checked by
    resolving each view's base classes per file, following imports,
    rather than by matching class names across the repo.

  * **from_embed keeps the buttons.** Migrating an embed+View pair by
    hand at 41 call sites is 41 chances to drop a component or leave it
    attached to a view that never gets sent. The helper moves them, and
    a select gets a row to itself -- five buttons fit in a row, a select
    does not share one.

  * **The emoji tables use the app's own emojis.** The bot owns 142 and
    was still reaching for the platform's white-on-grey ✅ / ❌ / ⚠️ in
    its central tables, which look different on every OS.

Run:  python3 tests/test_v2_and_emojis.py
"""

import ast
import os
import re
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


def py_files():
    for root, dirs, names in os.walk(BOT):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "tests"}]
        for name in names:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def parsed():
    out = {}
    for path in py_files():
        try:
            out[path] = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except SyntaxError:
            pass
    return out


def is_none(node):
    return isinstance(node, ast.Constant) and node.value is None


# ── 1. embeds and V2 must never share a message ─────────────────────


def test_no_embed_with_v2():
    print("\nAn embed is never sent with a V2 view")
    trees = parsed()

    def module_path(mod):
        cand = os.path.join(BOT, mod.replace(".", os.sep) + ".py")
        return cand if cand in trees else None

    def classes_in(path):
        return {
            n.name: [ast.unparse(b).split(".")[-1] for b in n.bases]
            for n in ast.walk(trees[path])
            if isinstance(n, ast.ClassDef)
        }

    def imports_in(path):
        out = {}
        for n in ast.walk(trees[path]):
            if isinstance(n, ast.ImportFrom) and n.module:
                src = module_path(n.module)
                if src:
                    for a in n.names:
                        out[a.asname or a.name] = (src, a.name)
        return out

    def is_v2(path, name, seen=None):
        """
        Resolved per file, following imports.

        A first attempt pooled every class in the repo into one
        namespace by bare name. Two different files each had an
        `AuthorOnlyView` -- one a plain discord.ui.View, one not -- and
        it reported five bugs that did not exist.
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

    clashes = []
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            emb = kw.get("embed", kw.get("embeds"))
            view = kw.get("view")
            if emb is None or view is None:
                continue
            if is_none(emb) or is_none(view):
                continue
            name = (
                ast.unparse(view.func).split(".")[-1]
                if isinstance(view, ast.Call)
                else (view.id if isinstance(view, ast.Name) else None)
            )
            # from_embed returns a Panel, which is a LayoutView. It is
            # a function, not a class, so the base-class walk cannot see
            # it -- and without this an `embed=x, view=from_embed(...)`
            # slipped straight through.
            if name == "from_embed" or (name and is_v2(path, name)):
                clashes.append(f"{os.path.relpath(path, BOT)}:{node.lineno}")

    check("no message carries both", not clashes,
          f"Discord rejects these: {clashes[:5]}")


# ── 2. the conversion helper ────────────────────────────────────────


def test_from_embed():
    print("\nfrom_embed keeps everything")
    import discord
    from discord.ui import View, Button, Select
    from utils.panels import from_embed

    def collect(panel):
        found = []

        def walk(item):
            if type(item).__name__ in ("Button", "Select"):
                found.append(item)
            for child in getattr(item, "children", []) or []:
                walk(child)

        for child in panel.children:
            walk(child)
        return found

    def texts(panel):
        out = []

        def walk(item):
            if type(item).__name__ == "TextDisplay":
                out.append(item.content)
            for child in getattr(item, "children", []) or []:
                walk(child)

        for child in panel.children:
            walk(child)
        return out

    embed = discord.Embed(title="Success", description="Banned in 3 of 5.",
                          color=0xFF0000)
    embed.add_field(name="Success Count", value="3 Guilds")
    embed.set_footer(text="by fufi")

    view = View(timeout=180)
    first = Button(label="List Successful")
    view.add_item(first)
    view.add_item(Button(label="List Unsuccessful"))

    panel = from_embed(embed, view)
    check("the result is a LayoutView",
          isinstance(panel, discord.ui.LayoutView))
    check("both buttons survive", len(collect(panel)) == 2)
    # A component belongs to one view at a time; leaving it on the old
    # view means discord.py routes its callback through a view nobody
    # ever sends.
    check("they are moved, not copied", len(view.children) == 0,
          "the old view still owns them")

    body = "\n".join(texts(panel))
    check("the title carries over", "Success" in body)
    check("the description too", "Banned in 3 of 5." in body)
    check("fields become text", "Success Count" in body and "3 Guilds" in body)
    check("and the footer", "by fufi" in body)

    accent = panel.children[0].accent_colour
    value = accent if isinstance(accent, int) else getattr(accent, "value", None)
    check("the colour is kept", value == 0xFF0000, f"got {value}")

    # Five buttons per row is the platform limit.
    many = View()
    for i in range(7):
        many.add_item(Button(label=f"b{i}"))
    rows = [c for c in from_embed(discord.Embed(title="t"), many).children[0].children
            if type(c).__name__ == "ActionRow"]
    check("buttons split into rows of five",
          [len(r.children) for r in rows] == [5, 2],
          f"got {[len(r.children) for r in rows]}")

    # A select occupies a whole row. Chunking purely by count raised
    # "maximum number of children exceeded" the moment one shared a row.
    mixed = View()
    mixed.add_item(Button(label="a"))
    mixed.add_item(Select(placeholder="p", options=[discord.SelectOption(label="x")]))
    mixed.add_item(Button(label="b"))
    rows = [c for c in from_embed(discord.Embed(title="t"), mixed).children[0].children
            if type(c).__name__ == "ActionRow"]
    shapes = [[type(i).__name__ for i in r.children] for r in rows]
    check("a select gets a row of its own",
          all(len(r) == 1 for r in shapes if "Select" in r),
          f"got {shapes}")

    check("it survives no view at all",
          from_embed(discord.Embed(title="t"), None) is not None)


# ── 3. custom emojis ────────────────────────────────────────────────


def test_emoji_tables():
    print("\nThe emoji tables use the app's own emojis")
    from utils import emoji as E

    for table in ("ACTION_EMOJIS", "BUTTON_EMOJIS", "MINECRAFT_EMOJIS"):
        values = getattr(E, table).values()
        unicode_left = [v for v in values if not str(v).startswith("<")]
        # 🎯 and ✏️ have no custom counterpart in the app's 142.
        unicode_left = [v for v in unicode_left if v not in ("🎯", "✏️")]
        check(f"{table} is custom throughout", not unicode_left,
              f"still platform emoji: {unicode_left}")

    check("success and error match in style",
          str(E.CHECK).startswith("<") and str(E.FAIL).startswith("<"),
          "one custom and one platform emoji from the same command")

    # PREVIOUS pointed at <:next:>, the same right-facing arrow as
    # NEXT_ALT1, so every "previous page" button showed a forward arrow.
    check("previous does not point forwards",
          E.PREVIOUS != E.NEXT and E.PREVIOUS != E.NEXT_ALT1,
          "the back button shows a forward arrow")
    check("previous is the app's back arrow", "zback" in E.PREVIOUS,
          f"got {E.PREVIOUS}")


def test_label_mapping():
    print("\nButton labels resolve to one emoji each")
    from utils.emoji import get_label_emoji as pick

    check("yes and no differ", pick("Yes") != pick("No"))
    check("cancel matches no", pick("Cancel") == pick("No"))

    # Exact keys are looked up directly, so "Edit Settings" never
    # reaches the substring pass -- testing it proves nothing about the
    # longest-match rule. Build a label that only the rule can resolve:
    # it contains both "edit" and "edit settings", and is neither.
    from utils.emoji import LABEL_EMOJIS
    both = "Please Edit Settings Now"
    contained = [k for k in LABEL_EMOJIS if k in both.lower()]
    check("the fixture really needs the rule",
          len(contained) > 1 and both.lower() not in LABEL_EMOJIS,
          f"only matched {contained}")
    check("the longest key wins",
          pick(both) == LABEL_EMOJIS["edit settings"],
          f'"{both}" fell back to a shorter key')
    check("previous and next differ", pick("◀ Previous") != pick("Next ▶"))
    # A wrong icon is worse than none.
    check("an unknown label gets nothing", pick("Quatsch") is None)
    check("so does an empty one", pick("") is None)
    # Calculator keys must stay bare.
    for key in ("1", "0", "+", "=", "/"):
        check(f"the {key!r} key stays bare", pick(key) is None)


def test_buttons_carry_emojis():
    print("\nThe buttons actually got them")
    total = with_emoji = 0
    for path, tree in parsed().items():
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
                kw = {k.arg: k for k in call.keywords if k.arg}
                label = kw.get("label")
                # Only literal labels were in scope; a runtime label
                # cannot be resolved from the source.
                if label is None or not isinstance(label.value, ast.Constant):
                    continue
                if not isinstance(label.value.value, str):
                    continue
                total += 1
                if "emoji" in kw:
                    with_emoji += 1

    print(f"\n  ({with_emoji} of {total} literal-label buttons carry an emoji)")
    check("most buttons now carry one", with_emoji >= total * 0.75,
          f"only {with_emoji}/{total}")

    # A ratio alone cannot see one button losing its icon -- 168 of 196
    # still clears any threshold. So every button whose label the table
    # *can* resolve has to actually carry one.
    from utils.emoji import get_label_emoji

    missing = []
    for path, tree in parsed().items():
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
                kw = {k.arg: k for k in call.keywords if k.arg}
                if "emoji" in kw:
                    continue
                label = kw.get("label")
                if label is None or not isinstance(label.value, ast.Constant):
                    continue
                if not isinstance(label.value.value, str):
                    continue
                if get_label_emoji(label.value.value):
                    missing.append(
                        f"{os.path.relpath(path, BOT)}:{call.lineno} "
                        f"{label.value.value!r}"
                    )

    check("no resolvable label was left bare", not missing,
          f"{len(missing)} button(s): {missing[:3]}")


def main():
    test_no_embed_with_v2()
    test_from_embed()
    test_emoji_tables()
    test_label_mapping()
    test_buttons_carry_emojis()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
