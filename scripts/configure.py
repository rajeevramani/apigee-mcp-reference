#!/usr/bin/env python3
"""Render customer-neutral templates for one Apigee environment."""

import argparse
import re
import shutil
from pathlib import Path

PLACEHOLDER_HOST = "YOUR_APIGEE_HOSTNAME"
PLACEHOLDER_ORG = "YOUR_APIGEE_ORG"
COPY_DIRS = ("apigee", "specs", "app")


def valid_hostname(value: str) -> str:
    value = value.strip().lower()
    if "://" in value or "/" in value or not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
        value,
    ):
        raise argparse.ArgumentTypeError("use a hostname only, for example api.example.com")
    return value


def valid_org(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise argparse.ArgumentTypeError("organisation must contain only letters, numbers, _ or -")
    return value


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--hostname", required=True, type=valid_hostname)
    parser.add_argument("--org", required=True, type=valid_org)
    parser.add_argument("--output", type=Path, default=repo / "build" / "configured")
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    if output == repo or repo in output.parents and output.name in COPY_DIRS:
        parser.error("output must be a separate working directory")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for name in COPY_DIRS:
        shutil.copytree(repo / name, output / name)

    replacements = {
        PLACEHOLDER_HOST: args.hostname,
        PLACEHOLDER_ORG: args.org,
    }
    changed = 0
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        rendered = text
        for old, new in replacements.items():
            rendered = rendered.replace(old, new)
        if rendered != text:
            path.write_text(rendered, encoding="utf-8")
            changed += 1

    remaining = []
    for path in output.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if PLACEHOLDER_HOST in text or PLACEHOLDER_ORG in text:
                remaining.append(path.relative_to(output))
    if remaining:
        raise SystemExit(f"unrendered placeholders remain: {', '.join(map(str, remaining))}")

    print(f"Rendered {changed} files into {output}")
    print("Next: python3 scripts/verify.py --root build/configured --configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
