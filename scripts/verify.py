#!/usr/bin/env python3
"""Validate public and environment-rendered Apigee MCP artifacts."""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

PLACEHOLDERS = ("YOUR_APIGEE_HOSTNAME", "YOUR_APIGEE_ORG")
FORBIDDEN = {}

REQUIRED = (
    "README.md",
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "app/mcp-tool-browser.html",
    "specs/mcp-tools.openapi.yaml",
    "specs/documentation-search-reverse-proxy.openapi.yaml",
    "specs/api-catalogue-search-reverse-proxy.openapi.yaml",
)


class StrictishHTMLParser(HTMLParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def read_text_files(root: Path):
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if path.is_file() and not {".git", "build", "dist", "__pycache__"}.intersection(relative_parts):
            try:
                yield path, path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"unexpected binary file: {path}") from exc


def fail(errors, message):
    errors.append(message)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=repo)
    parser.add_argument("--configured", action="store_true")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    errors = []

    if not root.is_dir():
        parser.error(f"root does not exist: {root}")

    if not args.configured:
        for relative in REQUIRED:
            if not (root / relative).is_file():
                fail(errors, f"missing required file: {relative}")

    files = list(read_text_files(root))
    combined = "\n".join(text for _, text in files)

    for label, pattern in FORBIDDEN.items():
        for path, text in files:
            if pattern.search(path.relative_to(root).as_posix()) or pattern.search(text):
                fail(errors, f"forbidden {label} in {path.relative_to(root)}")

    if args.configured:
        for placeholder in PLACEHOLDERS:
            if placeholder in combined:
                fail(errors, f"configured tree still contains {placeholder}")
    else:
        for placeholder in PLACEHOLDERS:
            if placeholder not in combined:
                fail(errors, f"public template is missing expected placeholder {placeholder}")

    xml_count = 0
    json_count = 0
    for path, text in files:
        suffix = path.suffix.lower()
        try:
            if suffix == ".xml":
                ET.fromstring(text)
                xml_count += 1
            elif suffix == ".json":
                json.loads(text)
                json_count += 1
            elif suffix == ".html":
                StrictishHTMLParser().feed(text)
        except Exception as exc:
            fail(errors, f"invalid {suffix or 'text'} in {path.relative_to(root)}: {exc}")

    pairs = (
        ("specs/mcp-tools.openapi.yaml", "apigee/mcp-discovery-proxy/apiproxy/resources/oas/mcp-tools.openapi.yaml"),
        ("specs/documentation-search-reverse-proxy.openapi.yaml", "apigee/documentation-search-mock/apiproxy/resources/oas/documentation-search-reverse-proxy.openapi.yaml"),
        ("specs/api-catalogue-search-reverse-proxy.openapi.yaml", "apigee/api-catalogue-search-mock/apiproxy/resources/oas/api-catalogue-search-reverse-proxy.openapi.yaml"),
    )
    for left, right in pairs:
        left_path, right_path = root / left, root / right
        if left_path.is_file() and right_path.is_file():
            if left_path.read_bytes() != right_path.read_bytes():
                fail(errors, f"OpenAPI copies differ: {left} != {right}")
        elif args.configured:
            fail(errors, f"missing OpenAPI pair: {left} or {right}")

    browser = root / "app" / "mcp-tool-browser.html"
    if browser.is_file():
        browser_text = browser.read_text(encoding="utf-8")
        for required in ("initialize", "tools/list", "tools/call", "x-api-key"):
            if required not in browser_text:
                fail(errors, f"browser client is missing {required}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: validated {len(files)} text files ({xml_count} XML, {json_count} JSON)")
    print("PASS: forbidden tenant/customer identifiers absent")
    print("PASS: OpenAPI source and embedded copies match")
    print("PASS: placeholder mode is correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
