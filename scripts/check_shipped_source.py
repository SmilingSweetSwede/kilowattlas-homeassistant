#!/usr/bin/env python3
"""Everything the Marketplace installs must be readable source that lives in this repository.

Run by .github/workflows/validate.yml on every push, and by hand before a
release:

    python3 scripts/check_shipped_source.py

It fails when a file under custom_components/ is

* generated or minified: a build header ("Generated", "Do not edit", a
  source map), or a line far longer than anyone writes by hand;
* built with a frontend framework or a build toolchain (Svelte, React, Vue,
  webpack, Vite, node_modules): Home Assistant custom integrations ship
  plain custom elements, and a framework means a build step whose input is
  somewhere else;
* pointing at another repository as its source (a sibling checkout such as
  map_framework_2, a relative path above this repository);

or when a build toolchain (package.json, vite/webpack/rollup/tsconfig config)
exists anywhere in the repository.

The Marketplace catalog's reviewers (hacs/default) check exactly this: anyone
must be able to read, and rebuild, what runs in their browser from what is in
the repository. The 1.0.0 release shipped a bundle built from a private
repository and was sent back.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / "custom_components"

# Code wider than this on one line is machine output, not source. The 1.0.0
# bundle had lines of 2,600 characters; a hand-written SVG path is under 800.
MAX_LINE = 1000

# (pattern, why) — matched case-insensitively against each shipped text file.
FORBIDDEN = [
    (r"^\s*(//|/\*|#|\*)\s*generated\b", "a build header: generated files are not source"),
    (r"do not edit", "a build header: the editable source is somewhere else"),
    (r"sourceMappingURL", "a source map: the file is compiled output"),
    (r"\bsvelte\b", "a frontend framework: Home Assistant panels are plain custom elements"),
    (r"\breact(-dom)?\b", "a frontend framework: Home Assistant panels are plain custom elements"),
    (r"\bvue(js)?\b", "a frontend framework: Home Assistant panels are plain custom elements"),
    (r"\bwebpack\b|\bvite\b|\brollup\b|\besbuild\b", "a build tool: there is no build step in this repository"),
    (r"node_modules", "a Node dependency: there is no build step in this repository"),
    (r"map_framework", "the private web app: nothing here may depend on it"),
    (r"\.\./\.\./", "a path above this repository: nothing here may depend on it"),
]

# Files that mean a build toolchain lives in this repository.
TOOLCHAIN = [
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "tsconfig.json",
    "vite.config.*",
    "webpack.config.*",
    "rollup.config.*",
    "svelte.config.*",
]

TEXT_SUFFIXES = {".js", ".mjs", ".css", ".html", ".py", ".json", ".yaml", ".yml", ".md", ".txt"}


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    rel = path.relative_to(ROOT)
    text = path.read_text(encoding="utf-8", errors="replace")
    # Translations and manifests hold words, not code: only the code rules apply there.
    code = path.suffix in {".js", ".mjs", ".css", ".html"}
    if code:
        for number, line in enumerate(text.splitlines(), 1):
            if len(line) > MAX_LINE:
                problems.append(f"{rel}:{number}: line is {len(line)} characters: minified or generated output")
                break
    for pattern, why in FORBIDDEN:
        if not code and "framework" in why:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if re.search(pattern, line, re.IGNORECASE):
                problems.append(f"{rel}:{number}: {why}\n    {line.strip()[:120]}")
                break
    return problems


def main() -> int:
    problems: list[str] = []
    for path in sorted(SHIPPED.rglob("*")):
        if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts:
            problems.extend(check_file(path))
    for pattern in TOOLCHAIN:
        for path in ROOT.rglob(pattern):
            if ".git" in path.parts or ".venv" in str(path):
                continue
            problems.append(f"{path.relative_to(ROOT)}: a build toolchain: this repository ships source only")
    if problems:
        print("Shipped files must be plain source kept in this repository:\n")
        print("\n".join(problems))
        print(f"\n{len(problems)} problem(s). See scripts/check_shipped_source.py for the rules.")
        return 1
    print("All shipped files are plain source kept in this repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
