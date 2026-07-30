#!/usr/bin/env python3
"""
The legal pages: imprint, privacy policy, terms.

These are the pages that carry legal weight, so the checks here are
mostly about honesty rather than layout.

What went wrong before, and what these tests exist to prevent:

  * The privacy policy claimed "All configuration data is AES-256
    encrypted at rest". It is not -- the data sits in plain SQLite
    files. The only thing in the project named "encryption" is a cog
    that base64-encodes text on request, which is neither encryption
    nor applied to stored data. A false claim about encryption in a
    privacy policy is the kind that matters after an incident.
  * The same page claimed the data is "distributed across global edge
    nodes". It runs in one container on one host.
  * Privacy and terms were English marketing copy on a German site,
    while the imprint next to them was proper German legalese.
  * Each page read the operator's details itself with its own fallback,
    so they could disagree with each other.
  * Two pages hard-coded the support invite and ignored
    NEXT_PUBLIC_SUPPORT_INVITE entirely.

Run:  python3 tests/test_legal_pages.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASHBOARD = os.path.join(ROOT, "dashboard")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*parts) -> str:
    path = os.path.join(DASHBOARD, *parts)
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_comments(source: str) -> str:
    """
    Drop comments before searching.

    Necessary here specifically: the comments in these files *quote* the
    wrong claims they replaced ("AES-256", "neural edge clusters") to
    explain why they are gone. Searching the raw text finds those
    quotations and reports the bug as still present.
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.S)
    return "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(("*", "//"))
    )


def visible_text(source: str) -> str:
    """
    Roughly what a reader sees: JSX tags removed, whitespace collapsed.

    Searching the raw file for a phrase is unreliable -- the formatter
    breaks lines wherever it likes, so "auf eurem eigenen Server" is
    split across two lines with an <em> in the middle and a plain
    substring search misses it. That cost one false failure here.
    """
    text = strip_comments(source)
    text = re.sub(r"<[^>]+>", " ", text)          # jsx tags
    text = re.sub(r"\{[^{}]*\}", " ", text)        # simple expressions
    text = text.replace("\\n", " ")
    return re.sub(r"\s+", " ", text)


PAGES = {
    "imprint": "app/imprint/page.tsx",
    "privacy": "app/privacy/page.tsx",
    "terms": "app/terms/page.tsx",
}


# ══════════════════════════════════════════════════════════════════════
#  Nothing untrue
# ══════════════════════════════════════════════════════════════════════


def test_no_false_claims():
    print("\nNo claims the code does not back up")

    privacy = strip_comments(read(PAGES["privacy"]))
    check("the privacy page exists", bool(privacy))
    if not privacy:
        return

    # The page mentions AES once, on purpose: it tells the reader the
    # old claim was wrong. That sentence is a correction, not a claim,
    # so a bare "AES" search reports the fix as the bug -- which it did
    # on the first run of this test.
    #
    # What must not exist is an *assertion* that the data is encrypted.
    # Checked as a claim in a positive sentence rather than as a word.
    claims = re.findall(
        r"[^.]*\b(?:AES|verschlüsselt)[^.]*\.", privacy, re.I
    )
    denials = [
        sentence for sentence in claims
        if not re.search(r"nicht|kein|vorher|falsch|stand", sentence, re.I)
    ]
    check("nothing asserts the data is encrypted",
          not denials,
          f"{denials[:1]} -- the databases are plain SQLite files; the "
          "only 'encryption' in the project is a base64 cog for user text")
    check("the page states plainly that it is not encrypted",
          "nicht zusätzlich" in privacy and "verschlüsselt" in privacy,
          "saying so is the point")
    check("and explains that the old claim was wrong",
          "vorher" in privacy and "falsch" in privacy,
          "a silent correction leaves anyone who read the old page "
          "still believing it")

    for phrase in ("edge nodes", "neural", "global edge"):
        check(f"no marketing claim: {phrase!r}",
              phrase.lower() not in privacy.lower(),
              "one container on one host")

    terms = strip_comments(read(PAGES["terms"]))
    check("the terms promise no uptime figure",
          "100%" not in terms and "100 %" not in terms,
          "a hobby project cannot promise uptime in its terms")
    for phrase in ("neural", "edge cluster", "deauthorization"):
        check(f"the terms drop {phrase!r}",
              phrase.lower() not in terms.lower(), "")


def test_pages_are_german():
    """
    The site is German and the imprint is German legalese. Terms and
    privacy being English marketing copy made them look like decoration
    rather than the documents people are held to.
    """
    print("\nThe pages are in German")

    for name in ("privacy", "terms"):
        body = strip_comments(read(PAGES[name]))
        english = ["Data Collection", "User Rights", "Terms of Service",
                   "Privacy Policy", "Last Modified", "Back to Home"]
        found = [phrase for phrase in english if phrase in body]
        check(f"{name}: no English headings left", not found, str(found))

        # A German legal page cites German law.
        check(f"{name}: cites the applicable rules",
              "DSGVO" in body or "deutsches Recht" in body or "DDG" in body,
              "")


# ══════════════════════════════════════════════════════════════════════
#  Everything comes from one place
# ══════════════════════════════════════════════════════════════════════


def test_single_source_of_truth():
    print("\nThe operator's details come from one module")

    legal = read("lib/legal.ts")
    check("there is a shared module", bool(legal))
    if not legal:
        return

    # Read by their unprefixed names -- the module accepts the
    # NEXT_PUBLIC_ spelling as a fallback, but that one only works if
    # the value was present during the docker build.
    for variable in (
        "IMPRINT_NAME",
        "IMPRINT_ADDRESS",
        "IMPRINT_EMAIL",
        "SUPPORT_INVITE",
        "BRAND_NAME",
    ):
        check(f"it reads {variable}", f'env("{variable}")' in legal, "")

    # Optional extras, so an operator who needs them does not have to
    # edit code.
    for variable in ("IMPRINT_VAT_ID", "PRIVACY_EMAIL", "HOSTER"):
        check(f"and the optional {variable}",
              f'env("{variable}")' in legal, "")

    check("and the NEXT_PUBLIC_ spelling still works",
          "NEXT_PUBLIC_" in legal,
          "that is what is configured today; dropping it would be a "
          "second bug on top of the first")

    for name, path in PAGES.items():
        body = strip_comments(read(path))
        own = re.findall(r"process\.env\.(\w+)", body)
        check(f"{name}: does not read the environment itself",
              not own,
              f"{own} -- a second fallback here is how two pages start "
              "disagreeing about who runs the service")
        check(f"{name}: imports the shared module",
              "@/lib/legal" in body, "")


def test_required_fields_have_no_fallback():
    """
    § 5 DDG wants a real name and a postal address. Those cannot be
    guessed, so there must be no default -- an imprint that looks filled
    in but is invented is worse than one that admits it is incomplete.
    """
    print("\nNothing legally required is invented")

    legal = read("lib/legal.ts")

    for name in ("OPERATOR", "ADDRESS", "EMAIL"):
        match = re.search(rf"export const {name} = ([^;]+);", legal, re.S)
        check(f"{name} is defined", match is not None, "")
        if not match:
            continue
        check(f"{name} has no fallback value",
              "||" not in match.group(1),
              f"{match.group(1).strip()} -- a made-up imprint is worse "
              "than an obviously incomplete one")

    # "." was what the address was actually set to in production. A
    # single character passes a truthiness check and produces an imprint
    # that looks complete.
    check("a placeholder like '.' counts as missing",
          '=== "."' in legal or "'.'" in legal,
          "an address of '.' satisfies `if (ADDRESS)` and satisfies "
          "nobody else")

    check("there is a completeness check",
          "imprintComplete" in legal and "missingFields" in legal, "")

    imprint = strip_comments(read(PAGES["imprint"]))
    # Both halves matter and they are separate mutations: importing the
    # helper without rendering the banner, or rendering a banner that
    # never asks whether anything is missing. Checking the two together
    # let a mutation through that removed only the call.
    check("the imprint imports the completeness helper",
          "missingFields" in imprint, "")
    check("and actually calls it",
          re.search(r"missingFields\s*\(", imprint) is not None,
          "importing it and never calling it renders no warning")
    check("and renders a warning from the result",
          "unvollständig" in imprint and "missing.length" in imprint,
          "a grey [missing] mid-page is easy to scroll past for months")
    check("and names the variables to set",
          "IMPRINT_NAME" in imprint,
          "so the fix does not need a developer")

    # The pages must render per request. As static pages they freeze
    # whatever was set during the docker build -- which is nothing,
    # since the Dockerfile passes only three NEXT_PUBLIC_ build args.
    # Setting the imprint in Railway then had no effect at all, which
    # is how an empty imprint survived being "configured".
    for name, path in PAGES.items():
        body = read(path)
        check(f"{name}: is rendered per request",
              'export const dynamic = "force-dynamic"' in body,
              "a static page bakes in the build-time environment, and "
              "the imprint is configured after the build")

    legal_src = read("lib/legal.ts")
    check("settings are read without the NEXT_PUBLIC_ prefix first",
          "process.env[name] ??" in legal_src,
          "NEXT_PUBLIC_* is inlined at build time; the unprefixed name "
          "is the one that works when set in Railway")


def test_support_link_is_configurable():
    """
    Two pages hard-coded the invite and ignored the variable, so setting
    it moved some links and not others.
    """
    print("\nThe support link is configurable everywhere")

    offenders = []
    for base, dirs, names in os.walk(os.path.join(DASHBOARD, "app")):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".next"}]
        for name in names:
            if not name.endswith(".tsx"):
                continue
            path = os.path.join(base, name)
            body = strip_comments(open(path, encoding="utf-8").read())
            # Per occurrence, not per file. Checking "does this file
            # mention SUPPORT_INVITE anywhere" passed a file that
            # imported it at the top and still hard-coded the link
            # further down -- which is exactly the bug being fixed.
            for line in body.splitlines():
                if "discord.gg/" not in line:
                    continue
                if "SUPPORT_INVITE" in line:
                    continue
                # The shared default lives in lib/legal.ts by design.
                offenders.append(
                    f"{os.path.relpath(path, DASHBOARD)}: {line.strip()[:60]}"
                )

    check("no page hard-codes the invite without the variable",
          not offenders, str(offenders))


# ══════════════════════════════════════════════════════════════════════
#  The privacy policy says what actually happens
# ══════════════════════════════════════════════════════════════════════


def test_privacy_content():
    print("\nThe privacy policy covers what it has to")

    body = strip_comments(read(PAGES["privacy"]))

    required = {
        "who is responsible": "Verantwortlich",
        "what is stored": "speichert",
        "how long": "lange",
        "the user's rights": "DSGVO",
        "the right to complain": "Art. 77",
        "the legal basis": "Art. 6",
        "third parties": "Discord Inc.",
        "the hoster": "HOSTER",
    }
    for label, needle in required.items():
        check(f"it covers {label}", needle in body, f"missing {needle!r}")

    # The specific promise that matters most to a server owner.
    check("it states message content is not stored",
          "nicht gespeichert" in body or "nicht mitgelesen" in body, "")
    # ...and names the one exception honestly. Checked on the substance,
    # not on the word: an "or" over two synonyms passed even when the
    # whole paragraph had been renamed away.
    prose = visible_text(read(PAGES["privacy"]))
    check("and names the logging exception",
          ("Logging" in prose or "Protokoll" in prose)
          and "gelöschte" in prose
          and "auf eurem eigenen Server" in prose,
          "claiming 'we never store messages' while a logging feature "
          "exists would be the same kind of lie as the AES claim")
    check("and says who is responsible for it",
          "selbst verantwortlich" in prose,
          "the admin who switches it on is the controller for that data")

    check("it links Discord's own policy",
          "discord.com/privacy" in body, "")
    check("it says data goes to the USA",
          "USA" in body and "Standardvertragsklauseln" in body,
          "a transfer to a US host needs naming under the GDPR")


def test_shared_layout():
    """All three pages use the same shell, so they look like one site."""
    print("\nOne consistent layout")

    for name, path in PAGES.items():
        body = read(path)
        check(f"{name}: uses the shared LegalPage shell",
              "LegalPage" in body and "@/components/legal-page" in body,
              "privacy and terms used to carry their own 40 lines of nav")
        check(f"{name}: carries a last-updated date",
              "LEGAL_UPDATED" in body,
              "a legal text without a date is hard to argue about")

    legal = read("lib/legal.ts")
    check("the date is defined once", legal.count("LEGAL_UPDATED") >= 1, "")
    check("and is not generated at runtime",
          "new Date()" not in legal,
          "'Stand: heute' on every page load says nothing")


def main():
    test_no_false_claims()
    test_pages_are_german()
    test_single_source_of_truth()
    test_required_fields_have_no_fallback()
    test_support_link_is_configurable()
    test_privacy_content()
    test_shared_layout()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
