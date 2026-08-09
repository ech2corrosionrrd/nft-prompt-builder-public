"""launchpad_service.py — Inspect & Validate .w3ir-nft.zip and Sugar bundles."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Dict, Optional

# Стеля РОЗПАКОВАНОГО розміру службового JSON. Стеля на сам архів не рятує від
# decompression bomb: кілобайтний zip розгортається в гігабайти, і `zf.read()`
# тягне це цілком у памʼять. Маніфест/конфіг колекції — десятки кілобайт.
MAX_JSON_MEMBER_BYTES = 2 * 1024 * 1024


def _read_json_member(zf: zipfile.ZipFile, name: str) -> Optional[Dict[str, Any]]:
    """Прочитати JSON-член архіву зі стелею розміру; будь-яка проблема → None."""
    try:
        if zf.getinfo(name).file_size > MAX_JSON_MEMBER_BYTES:
            return None
        with zf.open(name) as fh:
            # Читаємо на байт більше за стелю: захист від збрехавшого заголовка
            # (`file_size` бере з ZIP-директорії, її контролює той, хто пакував).
            raw = fh.read(MAX_JSON_MEMBER_BYTES + 1)
        if len(raw) > MAX_JSON_MEMBER_BYTES:
            return None
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def inspect_bundle_zip(zip_bytes: bytes) -> Dict[str, Any]:
    """Inspects uploaded ZIP bundle and returns collection metadata & readiness report."""
    if not zip_bytes:
        return {"valid": False, "error": "Empty ZIP file"}

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as e:
        return {"valid": False, "error": f"Invalid ZIP file format: {e}"}

    namelist = zf.namelist()

    # Zip-slip security guard
    for name in namelist:
        if name.startswith('/') or '..' in name or '\\' in name:
            return {"valid": False, "error": f"Security violation: dangerous path in zip: {name}"}

    has_manifest = "manifest.json" in namelist or any(n.endswith("manifest.json") for n in namelist)
    has_config = "config.json" in namelist or any(n.endswith("config.json") for n in namelist)

    assets_count = sum(1 for n in namelist if "assets/" in n and not n.endswith("/"))

    collection_name = "Custom Collection"
    symbol = "NFT"
    description = ""

    # 1. Try reading manifest.json
    manifest_name = next((n for n in namelist if n.endswith("manifest.json")), None)
    if manifest_name:
        m_data = _read_json_member(zf, manifest_name)
        if m_data:
            collection_name = m_data.get("name") or m_data.get("collection_name") or collection_name
            symbol = m_data.get("symbol") or symbol
            description = m_data.get("description") or description

    # 2. Try reading config.json (Sugar config)
    config_name = next((n for n in namelist if n.endswith("config.json")), None)
    if config_name:
        c_data = _read_json_member(zf, config_name)
        if c_data:
            if "number" in c_data:
                assets_count = c_data["number"]
            if "symbol" in c_data:
                symbol = c_data["symbol"]

    sugar_ready = has_config and assets_count > 0

    return {
        "valid": True,
        "collection_name": collection_name,
        "symbol": symbol,
        "description": description,
        "items_count": assets_count,
        "sugar_ready": sugar_ready,
        "has_manifest": has_manifest,
        "has_config": has_config,
        "total_files": len(namelist),
        "message": "Bundle valid and ready for launch." if sugar_ready else "Bundle inspected."
    }
