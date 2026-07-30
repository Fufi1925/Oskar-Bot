#!/usr/bin/env python3
"""
The CI workflow.

There was none: the test suite only ran when somebody remembered to run
it. A hand edit that turned a dict literal into a set shipped and
crash-looped the status bot -- locally a two second failure, in
production a broken deploy.

A workflow file is easy to write and easy to write *wrongly*, and a
broken one fails on GitHub rather than here. So the parts that can be
checked without GitHub are checked here: that the YAML parses, that
every command it runs exists, and that the versions match the ones the
container actually uses.

The one thing this cannot check is whether GitHub runs it. That only
shows on the first push.

Run:  python3 tests/test_ci_workflow.py
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "tests.yml")
BOOT_SCRIPT = os.path.join(ROOT, ".github", "scripts", "boot_test.py")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(path) -> str:
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8").read()


def load_workflow():
    try:
        import yaml
    except ImportError:
        return None
    return yaml.safe_load(read(WORKFLOW))


def all_steps(data) -> list[dict]:
    steps = []
    for job in (data.get("jobs") or {}).values():
        steps.extend(job.get("steps") or [])
    return steps


def all_run_commands(data) -> str:
    return "\n".join(step.get("run", "") for step in all_steps(data))


# ══════════════════════════════════════════════════════════════════════
#  The file itself
# ══════════════════════════════════════════════════════════════════════


def test_workflow_exists():
    print("\nThe workflow file")

    check("there is a workflow", os.path.exists(WORKFLOW), WORKFLOW)
    if not os.path.exists(WORKFLOW):
        return None

    data = load_workflow()
    if data is None:
        check("pyyaml is available to parse it", False,
              "install pyyaml to check the workflow properly")
        return None

    check("the YAML parses", isinstance(data, dict), str(type(data)))

    # `on:` is parsed as the boolean True by YAML 1.1. Both spellings
    # are accepted so this does not depend on the parser's mood.
    triggers = data.get("on", data.get(True))
    check("it has triggers", bool(triggers), str(list(data)))
    if triggers:
        check("it runs on push", "push" in triggers, str(list(triggers)))
        check("and on pull requests", "pull_request" in triggers,
              str(list(triggers)))
        check("and can be started by hand",
              "workflow_dispatch" in triggers,
              "useful when a run failed for an unrelated reason")

    jobs = data.get("jobs") or {}
    check("there is a bot job", "bot" in jobs, str(list(jobs)))
    check("and a dashboard job", "dashboard" in jobs, str(list(jobs)))

    for name, job in jobs.items():
        check(f"{name}: has a timeout",
              job.get("timeout-minutes") is not None,
              "a hung job otherwise burns the whole 6 hour default")

    check("runs are cancelled when superseded",
          bool(data.get("concurrency")),
          "a burst of commits otherwise queues runs nobody reads")

    check("permissions are read-only",
          (data.get("permissions") or {}).get("contents") == "read",
          "this workflow has no reason to write anything")

    return data


# ══════════════════════════════════════════════════════════════════════
#  What it runs has to exist
# ══════════════════════════════════════════════════════════════════════


def test_commands_exist(data):
    print("\nEverything it runs exists")

    if not data:
        return

    commands = all_run_commands(data)

    check("it runs the test suite", "tests/run_all.py" in commands, "")
    check("the test runner exists",
          os.path.exists(os.path.join(BOT, "tests", "run_all.py")), "")

    check("it runs the boot check", "boot_test.py" in commands, "")
    check("the boot script is in the repository",
          os.path.exists(BOOT_SCRIPT),
          "it used to live outside the repo, where CI cannot reach it")

    check("it type checks the dashboard", "tsc --noEmit" in commands, "")
    check("it builds the dashboard", "npm run build" in commands, "")
    check("it compiles every python file", "compileall" in commands,
          "most of the 145 cogs are imported by no test at all")

    # npx has picked the wrong package before and reported success
    # against nothing.
    check("tsc is called from node_modules, not through npx",
          "./node_modules/.bin/tsc" in commands and "npx tsc" not in commands,
          "npx tsc has resolved to a different package here before")

    # npm ci rather than npm install: the lock file must match.
    check("dependencies are installed with npm ci",
          "npm ci" in commands,
          "npm install would paper over a lock file that has drifted "
          "from package.json")


def test_versions_match_the_container(data):
    """
    CI has to test what actually ships.

    A different Python or Node major version here means a green build
    that says nothing about the image Railway runs.
    """
    print("\nVersions match the Dockerfile")

    if not data:
        return

    dockerfile = read(os.path.join(ROOT, "Dockerfile"))

    python_match = re.search(r"FROM python:(\d+\.\d+)", dockerfile)
    node_match = re.search(r"FROM node:(\d+)", dockerfile)

    check("the Dockerfile names a python version", python_match is not None, "")
    check("the Dockerfile names a node version", node_match is not None, "")

    raw = read(WORKFLOW)

    if python_match:
        version = python_match.group(1)
        check(f"CI tests python {version}, like the container",
              f'"{version}"' in raw,
              f"the image runs {version}; testing only something else "
              "proves nothing about the deployment")

    if node_match:
        major = node_match.group(1)
        check(f"CI uses node {major}, like the build stage",
              re.search(rf'node-version:\s*"{major}(\.\d+)?"', raw) is not None,
              f"the dashboard is built with node {major}")

    # next 14 declares engines.node >=18.17, so a bare "18" can resolve
    # to something it refuses to run on.
    package = read(os.path.join(ROOT, "dashboard", "package.json"))
    if '"next": "^14' in package:
        check("the node version is pinned past next's minimum",
              re.search(r'node-version:\s*"18\.\d+"', raw) is not None,
              "next 14 needs >=18.17; a bare \"18\" may resolve lower")


# ══════════════════════════════════════════════════════════════════════
#  The lint step has to be one that passes
# ══════════════════════════════════════════════════════════════════════


def test_no_network_is_honoured():
    """
    CI sets NO_NETWORK, and something has to read it.

    The workflow passed the variable from the first version, but no test
    looked at it -- so the first CI run fetched youtube.com for real. It
    passed, which is exactly why this was easy to miss: it works right
    up until YouTube is slow or rate-limits the runner, and then the
    build is red for a reason unrelated to the commit.
    """
    print("\nNO_NETWORK actually does something")

    raw = read(WORKFLOW)
    check("the workflow sets NO_NETWORK", "NO_NETWORK" in raw, "")

    readers = []
    tests_dir = os.path.join(BOT, "tests")
    for name in sorted(os.listdir(tests_dir)):
        if not name.endswith(".py"):
            continue
        if "NO_NETWORK" in read(os.path.join(tests_dir, name)):
            readers.append(name)

    check("and at least one test reads it", readers, str(readers))

    # The network tests are the reason it exists.
    check("the youtube test honours it",
          "test_youtube_notify.py" in readers,
          "it is the only suite that talks to the open internet")

    # Exercise it rather than grep for it: run the suite with the
    # variable set and confirm something is actually skipped.
    result = subprocess.run(
        [sys.executable, "tests/test_youtube_notify.py"],
        cwd=BOT, capture_output=True, text=True,
        env={**os.environ, "NO_NETWORK": "1"},
        timeout=300,
    )
    check("with NO_NETWORK the run still passes",
          result.returncode == 0, result.stdout[-300:])
    check("and it skips the network part",
          "skipped" in result.stdout and "0 failures" in result.stdout,
          result.stdout[-200:])
    check("without hitting youtube",
          "Against real YouTube" not in result.stdout
          or "no network" in result.stdout.lower(),
          result.stdout[-300:])


def test_lint_step_is_realistic():
    """
    A lint job that is red from day one is a lint job everybody learns
    to ignore, and then it catches nothing.

    The full F rule set reports 458 pre-existing findings in this
    codebase -- mostly unused imports, plus a false positive in a
    vendored package. So CI runs E9 (syntax errors) everywhere, which
    passes, and the full set only over the maintained files.
    """
    print("\nThe lint step passes on the current tree")

    raw = read(WORKFLOW)
    check("syntax errors are checked everywhere",
          "--select=E9 ." in raw, "")

    # Actually run it, rather than trusting the flag.
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select=E9", "."],
        cwd=BOT, capture_output=True, text=True,
    )
    if "No module named ruff" in result.stderr:
        print("  --   ruff not installed, skipping the live run")
    else:
        check("and that check passes right now",
              result.returncode == 0,
              result.stdout[-300:] or result.stderr[-300:])

    # The narrow list: every file named in it must exist, or CI fails
    # on a typo rather than on a real problem.
    listed = re.findall(r"^\s+((?:\.\./)?[\w./]+\.py|\.\./statusbot/)\s*\\?$",
                        raw, re.M)
    check("the maintained-files list is not empty", len(listed) > 3,
          str(listed))
    missing = [
        path for path in listed
        if not os.path.exists(os.path.join(BOT, path))
    ]
    check("every file in that list exists", not missing, str(missing))


def test_boot_script_fails_loudly():
    """
    The boot script's whole job is to fail when a cog does not load.

    The version this replaced printed its failures and then called
    os._exit(0) unconditionally -- fine for a human reading the output,
    useless in CI, which only looks at the exit code.
    """
    print("\nThe boot check can actually fail")

    source = read(BOOT_SCRIPT)
    check("the script exists", bool(source), BOOT_SCRIPT)
    if not source:
        return

    check("it returns non-zero when something fails to load",
          "return 1" in source, "")
    # Strip comments and docstrings first. This file's own docstring
    # quotes the old "os._exit(0)" to explain why it was wrong, and a
    # plain substring search reports the explanation as the bug -- which
    # it did on the first run of this test.
    import ast

    tree = ast.parse(source)
    code_only = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Docstrings and any other string literal.
            code_only = code_only.replace(node.value, "")

    check("it does not exit 0 unconditionally",
          "os._exit(0)" not in code_only,
          "that is exactly how the old one hid failures from CI")
    check("it passes its result to the exit code",
          "os._exit(code)" in source, "")
    # Behaviour, not text. Checking that "MINIMUM_COGS" appears
    # anywhere passed even with the comparison replaced by `if False`,
    # because the constant was still defined and mentioned in the
    # message. Run the real function with a stand-in bot instead.
    check("the minimum-cog guard is defined",
          "MINIMUM_COGS" in source, "")

    import asyncio
    import importlib.util

    spec = importlib.util.spec_from_file_location("_boot_check", BOOT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class EmptyBot:
        """A bot where every extension quietly loaded nothing."""

        cogs: dict = {}
        tree = type("T", (), {"get_commands": staticmethod(lambda: [])})()

        async def load_extension(self, name):
            return None

        def walk_commands(self):
            return []

    original = sys.modules.get("core.universitybot")
    try:
        fake = type(sys)("core.universitybot")
        fake.universitybot = EmptyBot
        fake.extensions = ["cogs"]
        sys.modules["core.universitybot"] = fake
        code = asyncio.run(module.main())
    finally:
        if original is not None:
            sys.modules["core.universitybot"] = original
        else:
            sys.modules.pop("core.universitybot", None)

    check("and it actually fails when no cogs load",
          code == 1,
          f"exit {code} -- an import error early in cogs/__init__.py "
          "drops everything after it, and the count is the only thing "
          "that notices")


def test_repository_metadata():
    """
    The files that say what this repository is.

    The repository was **public** until this was checked -- the whole
    source readable by anyone, while the website had just been scrubbed
    of every link to it. Scrubbing the links was pointless while the
    repository itself was open, and nobody had noticed because nothing
    ever asserted it.

    That is fixed at GitHub, which these tests cannot see. What they can
    check is that the files in the tree agree: a licence that reserves
    rights, a README that does not promise MIT, and a security policy
    that says where to report instead of opening an issue.
    """
    print("\nRepository metadata")

    licence = read(os.path.join(ROOT, "LICENSE"))
    check("there is a LICENSE file", bool(licence), "")
    if licence:
        check("it reserves all rights",
              "All Rights Reserved" in licence, licence[:80])
        check("and does not grant a licence",
              "No permission is granted" in licence, "")
        check("MIT is not mentioned as the licence",
              "MIT License" not in licence and "MIT license" not in licence,
              "the README claimed MIT, which would have let anyone "
              "copy and redistribute the code")
        check("access to the repo is not a licence",
              "does not constitute a licence" in licence,
              "somebody who gets in should not think that is permission")

    readme = read(os.path.join(ROOT, "README.md"))
    # Blockquote lines dropped first: the README quotes the old "MIT
    # License" to say it was wrong, and a plain search reports the
    # correction as the bug. Third time this pattern has bitten in this
    # project, hence the note.
    readme_claims = "\n".join(
        line for line in readme.splitlines() if not line.lstrip().startswith(">")
    )
    check("the README does not claim MIT",
          "MIT License" not in readme_claims,
          "it did; the same false claim was in the imprint")
    check("and it does say the rights are reserved",
          "Alle Rechte vorbehalten" in readme_claims, "")
    check("it points at the LICENSE file",
          "LICENSE" in readme, "")
    check("and says pull requests are not taken",
          "Pull Requests" in readme or "Pull-Requests" in readme, "")

    # GitHub reads .github/SECURITY.md for the "report a vulnerability"
    # link. The SECURITY.md in the root is architecture documentation
    # that predates this -- I overwrote it once by assuming the name
    # meant the same thing, so both are checked and cross-linked.
    security = read(os.path.join(ROOT, ".github", "SECURITY.md"))
    check("there is a reporting policy", bool(security),
          ".github/SECURITY.md is what GitHub surfaces")

    architecture = read(os.path.join(ROOT, "SECURITY.md"))
    check("the architecture notes are still there",
          "Security & Architecture Notes" in architecture,
          "this file documents how auth and the feature flags work")
    check("and the two point at each other",
          ".github/SECURITY.md" in architecture
          and "../SECURITY.md" in security,
          "two files with the same name need to say which is which")
    if security:
        check("it says not to open a public issue",
              "nicht als öffentliches Issue" in security
              or "NICHT als öffentliches Issue" in security,
              "a public issue explains the attack before it is fixed")
        check("it names a private route",
              "Direktnachricht" in security or "E-Mail" in security, "")
        check("it says to revoke first when a secret leaks",
              "widerrufen" in security,
              "deleting a secret from a file leaves it in the history; "
              "revoking is the part that actually helps")


def test_github_config_parses():
    """
    Every YAML under .github/ has to parse.

    A broken issue template does not fail loudly -- GitHub just silently
    stops offering it, which nobody notices for months.
    """
    print("\nThe .github configuration")

    try:
        import yaml
    except ImportError:
        print("  --   pyyaml missing, skipping")
        return

    github = os.path.join(ROOT, ".github")
    found = []
    for base, dirs, names in os.walk(github):
        for name in names:
            if name.endswith((".yml", ".yaml")):
                found.append(os.path.join(base, name))

    check("there are config files", len(found) >= 3, str(len(found)))

    for path in found:
        rel = os.path.relpath(path, ROOT)
        try:
            yaml.safe_load(read(path))
            check(f"{rel} parses", True)
        except Exception as err:  # noqa: BLE001
            check(f"{rel} parses", False, str(err)[:120])

    dependabot = read(os.path.join(github, "dependabot.yml"))
    check("dependabot is configured", bool(dependabot), "")
    if dependabot:
        for ecosystem in ("pip", "npm", "github-actions"):
            check(f"it watches {ecosystem}", ecosystem in dependabot, "")
        check("updates are grouped, not one PR per package",
              "groups:" in dependabot,
              "a PR per package every week gets closed unread")

    templates = os.path.join(github, "ISSUE_TEMPLATE")
    check("there are issue templates", os.path.isdir(templates), "")
    if os.path.isdir(templates):
        config = read(os.path.join(templates, "config.yml"))
        check("the security policy is linked from the issue picker",
              "SECURITY.md" in config,
              "the moment somebody opens an issue is the moment to say "
              "'not this way' for security reports")
        bug = read(os.path.join(templates, "bug.yml"))
        check("the bug form asks for the guild id",
              "Server-ID" in bug,
              "without it nothing can be found in the logs")


def main():
    data = test_workflow_exists()
    test_commands_exist(data)
    test_versions_match_the_container(data)
    test_no_network_is_honoured()
    test_lint_step_is_realistic()
    test_boot_script_fails_loudly()
    test_repository_metadata()
    test_github_config_parses()

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
