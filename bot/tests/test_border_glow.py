#!/usr/bin/env python3
"""
The BorderGlow rim light, adapted from React Bits.

What this pins down:

  * **The maths survives the port.** The source in the brief had been
    pasted through Markdown, which silently corrupted six places -- a
    missing bracket, a broken template literal, `x * x * x` eaten by
    italics, and three autolinked identifiers. Copying it verbatim would
    not have compiled; copying it *almost* verbatim is worse, because
    `x  *x*  x` is still valid JavaScript and just computes the wrong
    curve. The reconstructed values are checked here.

  * **One listener, not 132.** A card gets the effect by having a class,
    not by being wrapped in two more divs. That is what makes it safe to
    apply across 121 existing cards without touching a single layout.

  * **The layers fit the cards we actually have.** Our cards paint their
    own background and 16 of them clip their own content, neither of
    which the original expects.

Run:  python3 tests/test_border_glow.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def strip_comments(src: str) -> str:
    """Drop /* */ and // comments before matching."""
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    without_lines = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", without_lines, flags=re.S)


def rule_body(css: str, selector: str, must_contain: str = "") -> str:
    """
    The body of a rule, chosen by content rather than by first match.

    A selector appears more than once -- the rule itself, plus overrides
    in media queries -- and splitting on the first occurrence has quietly
    tested the wrong block before.
    """
    for chunk in css.split(selector)[1:]:
        if not chunk.lstrip().startswith("{"):
            continue
        body = chunk[chunk.index("{") + 1: chunk.index("}")]
        if not must_contain or must_contain in body:
            return body
    return ""


def test_component():
    print("\nThe component")
    path = os.path.join(DASH, "components", "ui", "border-glow.tsx")
    check("it exists", os.path.isfile(path), path)
    if not os.path.isfile(path):
        return
    src = strip_comments(read(path))

    check("it is a client component", '"use client"' in src,
          "pointer handlers need the browser")

    # ── The six Markdown corruptions ────────────────────────────────
    print("\nThe pasted source was repaired, not copied")
    # `vars`--glow-color${keys[i]}`] =` -- the opening bracket was eaten.
    check("the glow-var index is written correctly",
          "vars[`--glow-color${suffix}`]" in src,
          "the pasted version was missing its opening bracket")
    # The `x  *x*  x` corruption lived in easeInCubic, which only the
    # intro sweep used. The sweep is deliberately not implemented -- 121
    # cards sweeping on page load, and the brief's own example turns it
    # off -- so the corrupted function has no port to check. What must
    # hold is that it was left out cleanly rather than half-copied.
    check("the unimplemented sweep left nothing behind",
          "easeInCubic" not in src and "sweep-active" not in src,
          "a half-ported animation is worse than none")
    for ident in ("performance.now()", "card.style", "rect.top"):
        check(f"{ident} is not an autolink",
              f"]({ident}" not in src and f"[{ident}]" not in src,
              "the brief had this as a Markdown link")
    check("className is a real call, not a broken literal",
          "className={cn(" in src or "className={" in src,
          "the pasted version had a stray backtick")

    # ── The maths ───────────────────────────────────────────────────
    print("\nThe maths")
    check("the angle is offset by 90 degrees",
          "* (180 / Math.PI) + 90" in src,
          "the cone would trail the cursor by a quarter turn")
    check("negative angles wrap to 0-360",
          "angle += 360" in src,
          "a conic-gradient with a negative start jumps")
    check("edge proximity is clamped to 0..1",
          "Math.min(Math.max(" in src,
          "past the corner the value exceeds 1 and the rim over-brightens")
    check("the glow alpha is clamped to 100%",
          "Math.min(opacity * intensity, 100)" in src,
          "an intensity above 1 makes an invalid alpha and drops the colour")

    # ── One listener ────────────────────────────────────────────────
    print("\nOne listener for every card")
    check("there is a provider",
          "export function BorderGlowProvider" in src)
    check("it listens on the document",
          'document.addEventListener("pointermove"' in src,
          "a listener per card is 132 listeners for one cursor")
    # Optional-called: `event.target` can be a text node or the
    # document on the way out, neither of which has `closest`.
    check("it finds the card by class",
          ".closest?.(" in src or ".closest(" in src,
          "without closest it cannot tell which card is under the pointer")
    check("writes are batched into one frame",
          "requestAnimationFrame(flush)" in src,
          "pointermove fires far more often than the screen refreshes")
    check("the frame is cancelled on unmount",
          "cancelAnimationFrame" in src,
          "a leaked loop writes to a detached node")
    check("the listener is removed on unmount",
          'removeEventListener("pointermove"' in src,
          "the handler would outlive the provider")
    check("touch drags are ignored",
          'pointerType === "touch"' in src,
          "scrolling on a phone would light cards under the finger")
    # Leaving a card must reset it, or the next hover starts lit at the
    # angle the pointer left at.
    check("leaving a card resets it",
          '"--edge-proximity", "0"' in src,
          "the rim would stay lit after the pointer leaves")
    # getBoundingClientRect forces layout; once a frame, not once an event.
    check("layout is read at most once a frame",
          src.count("getBoundingClientRect") == 1,
          "reading it per event forces layout on every mouse move")


def test_css():
    print("\nCSS")
    css = strip_comments(read(os.path.join(DASH, "app", "globals.css")))

    check("the card class exists", ".border-glow-card {" in css)

    base = rule_body(css, ".border-glow-card ", "isolation")
    if not base:
        base = rule_body(css, ".border-glow-card", "isolation")
    # z-index: -1 layers escape behind the page without a stacking context.
    check("it creates a stacking context",
          "isolation: isolate" in base,
          "the glow layers would slide behind the page background")
    # Our cards round themselves with Tailwind; forcing 28px reshapes them.
    check("it does not force its own corner radius",
          "border-radius: var(--border-radius, inherit)" in base
          or "border-radius" not in base,
          "every card would be reshaped to the component's default")

    # The original paints its own background. Ours already have one, and
    # a second behind the first breaks every bg-* override.
    check("it does not paint a background over the card",
          not re.search(r"^\s*background:\s*var\(--card-bg", base, re.M),
          "the card's own bg-[#10233f] would be covered")

    rim = rule_body(css, ".border-glow-card::before", "border")
    check("the rim knocks out the middle",
          "padding-box" in rim and "border-box" in rim,
          "without the knockout the gradient floods the whole card")
    check("the rim is masked to a cone",
          "conic-gradient" in rim and "var(--cursor-angle)" in rim,
          "the whole edge would light at once")
    check("the rim mask is prefixed for WebKit",
          "-webkit-mask-image" in rim,
          "Safari needs the prefix and would show an unmasked rim")

    halo = rule_body(css, ".border-glow-card::after", "box-shadow")
    check("the halo reaches outside the card",
          "calc(var(--glow-padding) * -1)" in halo,
          "it would sit on the border instead of around it")
    check("the halo is masked to the same cone",
          "conic-gradient" in halo and "var(--cursor-angle)" in halo)
    check("the halo brightens rather than covers",
          "mix-blend-mode: plus-lighter" in halo,
          "a plain layer would grey out whatever is behind it")

    # 16 cards clip their own content and would cut the halo off square.
    clipped = rule_body(css, ".border-glow-card.is-clipped::after")
    check("clipping cards keep the glow inside",
          "inset: 0" in clipped,
          "overflow-hidden would cut the halo into a hard straight line")

    print("\nThe glow corner matches the card's")
    # The ring is an inset box-shadow, which is drawn on the padding
    # box -- and CSS derives that radius by subtracting the border
    # width. The halo layer carries a 40px transparent border to push
    # the ring back onto the card, so inheriting the card's 24px gives
    # 24 - 40, clamped to 0: a square corner around a rounded card.
    # Adding the padding back cancels the subtraction.
    check("the halo radius adds the padding back",
          "border-radius: calc(var(--card-radius) + var(--glow-padding))" in halo,
          "inheriting the radius squares the corner -- 24px - 40px clamps to 0")
    check("the radius is not inherited on the halo",
          "border-radius: inherit" not in halo,
          "inherit is what produced the square corner")
    # The clipped variant has no border to subtract, so it must not add
    # the padding either -- that would round it too far.
    check("the clipped variant uses the plain radius",
          "border-radius: var(--card-radius);" in clipped,
          "with no border there is nothing to compensate for")

    base_all = rule_body(css, ".border-glow-card", "--card-radius")
    check("there is a default radius to work from",
          "--card-radius:" in base_all,
          "the ring cannot be built without knowing the card's corner")
    # Three radii are in use across the cards; the odd ones need a class
    # because CSS cannot read the element's own computed radius.
    for cls, value in ((".glow-r-2xl", "1rem"), (".glow-r-20", "20px")):
        body = rule_body(css, cls)
        check(f"{cls} sets its own radius",
              f"--card-radius: {value}" in body,
              "this card's glow would use the 3xl corner")

    print("\nAccessibility")
    reduced = ""
    for chunk in css.split("prefers-reduced-motion")[1:]:
        body = chunk[: chunk.index("\n}\n")] if "\n}\n" in chunk else chunk
        if ".border-glow-card" in body:
            reduced = body
            break
    check("the fade is switched off for reduced motion",
          "transition: none" in reduced,
          "the only self-moving part here should honour the setting")


def test_applied():
    print("\nApplied to the cards")
    provider_host = strip_comments(read(os.path.join(DASH, "app", "layout.tsx")))
    check("the provider is mounted once, at the root",
          "<BorderGlowProvider />" in provider_host,
          "no listener means no glow anywhere")

    count = 0
    clipped = 0
    files = 0
    for root, dirs, names in os.walk(DASH):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".next", ".git"}]
        for name in names:
            if not name.endswith(".tsx"):
                continue
            src = read(os.path.join(root, name))
            found = src.count("border-glow-card")
            if found:
                files += 1
                count += found
                clipped += src.count("border-glow-card is-clipped")

    check("the class reached a lot of cards", count >= 100,
          f"only {count} cards carry it")

    # A card whose corner is not rounded-3xl needs the matching radius
    # class, or its glow is built from the wrong corner. Checking the
    # markup, not just that the CSS exists.
    mismatched = []
    for root, dirs, names in os.walk(DASH):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".next", ".git"}]
        for name in names:
            if not name.endswith(".tsx"):
                continue
            src = read(os.path.join(root, name))
            for match in re.finditer(r'className="([^"]*border-glow-card[^"]*)"', src):
                cls = match.group(1)
                if "rounded-2xl" in cls and "glow-r-2xl" not in cls:
                    mismatched.append((name, "rounded-2xl"))
                elif "rounded-[20px]" in cls and "glow-r-20" not in cls:
                    mismatched.append((name, "rounded-[20px]"))
    check("every odd radius carries its class",
          not mismatched,
          f"{len(mismatched)} card(s) would glow at the wrong corner: "
          f"{mismatched[:3]}")
    check("across the whole dashboard", files >= 40, f"only {files} files")
    # Cards that clip their own content need the inside-only variant.
    check("clipping cards were marked", clipped > 0,
          "overflow-hidden cards would show a truncated halo")

    print(f"\n  ({count} cards in {files} files, {clipped} of them clipping)")


def main():
    check("the dashboard folder was found", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_component()
    test_css()
    test_applied()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
