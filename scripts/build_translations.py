#!/usr/bin/env python3
"""Generate translations/en.json from strings.json for the HACS build.

Home Assistant core resolves `[%key:...%]` references and ships translations
via Lokalise; a custom component loads translations/<lang>.json directly, so
the references must be expanded here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "kilowattlas"

COMMON = {
    "common::config_flow::error::cannot_connect": "Failed to connect",
    "common::config_flow::abort::already_configured_service": (
        "Service is already configured"
    ),
    "common::config_flow::abort::reauth_successful": (
        "Re-authentication was successful"
    ),
    "common::config_flow::abort::reconfigure_successful": (
        "Re-configuration was successful"
    ),
}

REF = re.compile(r"\[%key:(.+?)%\]")


def lookup(strings: dict, key: str) -> str:
    if key in COMMON:
        return COMMON[key]
    prefix = "component::kilowattlas::"
    if not key.startswith(prefix):
        sys.exit(f"unknown reference {key}")
    node: object = strings
    for part in key[len(prefix) :].split("::"):
        node = node[part]  # type: ignore[index]
    return expand(strings, node)  # type: ignore[arg-type]


def expand(strings: dict, node):  # noqa: ANN001, ANN201
    if isinstance(node, dict):
        return {k: expand(strings, v) for k, v in node.items()}
    if isinstance(node, str):
        return REF.sub(lambda m: lookup(strings, m.group(1)), node)
    return node


def main() -> None:
    strings = json.loads((COMPONENT / "strings.json").read_text())
    out = COMPONENT / "translations" / "en.json"
    out.write_text(
        json.dumps(expand(strings, strings), indent=2, ensure_ascii=False) + "\n"
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
