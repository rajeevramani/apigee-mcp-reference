#!/usr/bin/env python3
"""Package Apigee proxy directories as importable ZIP archives."""

import argparse
import json
import shutil
import zipfile
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=repo / "build" / "configured" / "apigee")
    parser.add_argument("--output", type=Path, default=repo / "dist")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_dir():
        parser.error(f"source does not exist: {source}; run scripts/configure.py first")

    output.mkdir(parents=True, exist_ok=True)
    for old_zip in output.glob("*.zip"):
        old_zip.unlink()

    packaged = []
    for proxy_dir in sorted(source.iterdir()):
        bundle = proxy_dir / "apiproxy"
        if not bundle.is_dir():
            continue
        destination = output / f"{proxy_dir.name}.zip"
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(proxy_dir))
        packaged.append(destination)

    products_source = source / "api-products"
    products_output = output / "api-products"
    if products_output.exists():
        shutil.rmtree(products_output)
    if products_source.is_dir():
        products_output.mkdir()
        for product in sorted(products_source.glob("*.json")):
            json.loads(product.read_text(encoding="utf-8"))
            shutil.copy2(product, products_output / product.name)

    if not packaged:
        raise SystemExit("no proxy bundles found")

    print(f"Packaged {len(packaged)} proxies:")
    for path in packaged:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
