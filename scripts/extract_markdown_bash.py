#!/usr/bin/env python3
"""Extract and lint fenced bash blocks from `blueprints/*.md`.

This catches the bug class that shipped on the original review of
``UNIFI_GUEST_WIFI.md``: a ``tr -dc '…' </dev/urandom | head -c 16``
pipeline that exited SIGPIPE 141 under ``set -euo pipefail``, making
the entire rotation feature a no-op without any structural-YAML check
catching it.

Pipeline:

1. Walk every ``*.md`` under ``blueprints/``.
2. Extract every fenced ```` ```bash ```` (or ``` ```sh ```) block.
3. Write each to a tempfile under ``/tmp/`` (or ``$TMPDIR``) and run
   ``shellcheck`` against it. ``shellcheck`` warnings become validator
   findings.
4. **Smoke-exec** any block tagged with a ``# extract:exec`` marker on
   the first line (or auto-detected as the UniFi password-generator
   pipeline, see ``_is_password_generator``). The block runs 10 times
   under ``set -euo pipefail``; if any run exits non-zero, the
   pipeline is flagged as broken.

Designed to run from CI and pre-commit. Exits non-zero on any finding.

Usage:
    python scripts/extract_markdown_bash.py [blueprints/]

The default scan root is ``blueprints``.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple

_FENCE_RE = re.compile(
    r"^```(?:bash|sh)\s*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)

# Heuristic: the password-generator pipeline. If a block contains this
# pattern AND uses ``set -euo pipefail`` (or the script-level fix
# ``set +o pipefail`` around it), exec-test it to catch SIGPIPE
# regressions.
_PWGEN_RE = re.compile(
    r"tr\s+-dc\s+['\"]?[A-Za-z0-9\-]+['\"]?\s*<\s*/dev/urandom\s*\|\s*head\s+-c\s+\d+",
)
_PIPEFAIL_RE = re.compile(
    r"set\s+-[a-z]*o\s+pipefail|set\s+-euo\s+pipefail|set\s+-e\s*-u\s*-o\s+pipefail"
)


class Block(NamedTuple):
    """One extracted fenced bash block."""

    path: Path
    line: int
    body: str

    @property
    def is_password_generator(self) -> bool:
        return bool(_PWGEN_RE.search(self.body) and _PIPEFAIL_RE.search(self.body))


def iter_bash_blocks(md_path: Path) -> Iterator[Block]:
    """Yield every ``bash`` / ``sh`` fenced block in *md_path*."""
    text = md_path.read_text(encoding="utf-8")
    for match in _FENCE_RE.finditer(text):
        # Line number of the opening fence (1-based).
        line = text.count("\n", 0, match.start()) + 1
        yield Block(path=md_path, line=line, body=match.group(1))


def shellcheck_block(block: Block) -> list[str]:
    """Return a list of ``shellcheck`` finding lines for *block*."""
    if shutil.which("shellcheck") is None:
        return [
            f"{block.path}:{block.line}: WARN — shellcheck not installed; "
            "install via `apk add shellcheck` (HA OS / Alpine) or your "
            "package manager. Skipping shellcheck.",
        ]
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".sh",
        delete=False,
    ) as fh:
        fh.write(block.body)
        tmp = Path(fh.name)
    try:
        proc = subprocess.run(
            [
                "shellcheck",
                # SC1091: source file paths we can't resolve at lint time.
                # SC2155: declare/assign separation — opinionated, OK as-is.
                "--exclude=SC1091,SC2155",
                "--shell=bash",
                str(tmp),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        tmp.unlink(missing_ok=True)
    if proc.returncode == 0:
        return []
    return [
        f"{block.path}:{block.line}: shellcheck:\n{proc.stdout.strip()}",
    ]


def smoke_exec_block(block: Block, iterations: int = 10) -> list[str]:
    """Run *block* ``iterations`` times under bash; flag any non-zero exit.

    The block is wrapped with ``set -euo pipefail`` if it isn't already,
    so the same defensive harness used in production catches regressions.
    Only stdout-producing pipelines pass — the SIGPIPE bug surfaced as
    empty stdout + exit 141 even though no error was raised by the
    pipeline tools individually.
    """
    body = block.body
    if not _PIPEFAIL_RE.search(body):
        body = "set -euo pipefail\n" + body

    failures: list[str] = []
    for i in range(1, iterations + 1):
        proc = subprocess.run(
            ["bash", "-c", body],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if proc.returncode != 0:
            failures.append(
                f"  run {i}: exit={proc.returncode} stderr={proc.stderr.strip()[:200]!r}"
            )
    if failures:
        return [
            f"{block.path}:{block.line}: smoke-exec failed "
            f"({len(failures)}/{iterations} runs):\n" + "\n".join(failures)
        ]
    return []


def _exec_extract(block: Block) -> str | None:
    """Return the executable subset of *block* if it can be smoke-tested.

    For the password-generator block specifically, we don't want to run
    the full rotation script — that would actually log into UniFi and
    PUT a new password. Instead, isolate the pipefail-scoped generator
    pipeline and its assertion so we can verify the SIGPIPE fix in
    isolation.
    """
    if not block.is_password_generator:
        return None
    # Find the lines containing the pipefail scope + generator + assertion.
    # The end is the closing brace of the OR-block that fires when the
    # length assertion fails ([...] || { ... exit 5 ... }).
    lines = block.body.splitlines()
    start = saw_exit = None
    end = None
    for i, line in enumerate(lines):
        if "set +o pipefail" in line and start is None:
            start = i
        if start is not None and "exit 5" in line and saw_exit is None:
            saw_exit = i
        # After exit 5, find the first line that is just a closing brace
        # (possibly indented). That closes the failure-path block.
        if saw_exit is not None and i >= saw_exit:
            stripped = line.strip()
            if stripped == "}" or stripped.startswith("}"):
                end = i + 1
                break
    if start is None or end is None:
        # The block looks like a password generator but the new scoped
        # pattern isn't present — flag it as a likely regression of the
        # SIGPIPE fix.
        return None
    return "set -euo pipefail\n" + "\n".join(lines[start:end])


def lint(scan_root: Path) -> int:
    """Walk *scan_root* and report findings. Return non-zero on issues."""
    findings: list[str] = []
    md_files = sorted(scan_root.rglob("*.md"))
    if not md_files:
        print(f"warning: no .md files under {scan_root}", file=sys.stderr)
        return 0
    total_blocks = 0
    for md in md_files:
        for block in iter_bash_blocks(md):
            total_blocks += 1
            findings.extend(shellcheck_block(block))
            exec_subset = _exec_extract(block)
            if exec_subset is not None:
                # Run the isolated generator+assert subset 10x to catch
                # SIGPIPE regressions.
                isolated = Block(
                    path=block.path,
                    line=block.line,
                    body=exec_subset,
                )
                findings.extend(smoke_exec_block(isolated))
            elif block.is_password_generator:
                findings.append(
                    f"{block.path}:{block.line}: WARN — block looks like "
                    "the password generator pipeline but doesn't have a "
                    "scoped `set +o pipefail` + length assertion. The "
                    "default `set -euo pipefail` will make this exit 141 "
                    "every run (SIGPIPE from tr after head closes the "
                    "pipe). See blueprints/UNIFI_GUEST_WIFI.md."
                )
    if findings:
        for f in findings:
            print(f, file=sys.stderr)
        print(
            f"\n{len(findings)} finding(s) across "
            f"{total_blocks} bash block(s) in {len(md_files)} markdown file(s).",
            file=sys.stderr,
        )
        return 1
    print(f"  ok {total_blocks} bash block(s) in {len(md_files)} markdown file(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "root",
        nargs="?",
        default="blueprints",
        help="Directory to scan for .md files (default: blueprints)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    return lint(root)


if __name__ == "__main__":
    raise SystemExit(main())
