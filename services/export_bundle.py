"""Збірка mint-ready бандла під різні платформи (без мінту в застосунку).

Новий курс: застосунок створює *контент, готовий до мінту*, а користувач сам
обирає, де мінтити. Цей модуль пакує зображення + метадані у формат конкретної
платформи й віддає ZIP (локально) або шар для IPFS-папки (`ipfs.upload_directory`).

Чисті функції (без Streamlit) — UI лише викликає `build_zip` / `ipfs_publish`.
Метадані будуються через `services.web3_service` (ERC-721 / Metaplex), тож
зберігаються Prompt-Lock і provenance-атрибути, як і при прямому мінті.

Підтримувані платформи (PLATFORMS):
- opensea   — ERC-721/OpenSea, 1-індексовано: images/<n>.png + metadata/<n>.json
- metaplex  — Metaplex/Candy Machine (sugar), 0-індексовано: assets/<i>.png + assets/<i>.json
- thirdweb  — thirdweb «Batch Upload»: images/<i>.png + metadata.csv
- generic   — універсальний images/ + metadata/ + collection.json
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone

import ipfs
from i18n import trait_type_en
from metadata_provenance import add_rarity_ranks
from trait_i18n import to_product_en
from services import web3_service
from services.zip_readme import zip_readme

# Attribution «Made with w3ir» — віральна петля G3.1: кожен опублікований деінде
# бандл несе посилання назад. Лише у супровідних файлах/метаданих, НЕ в пікселях.
ATTRIBUTION_TEXT = "Made with w3ir.io"
ATTRIBUTION_URL = "https://w3ir.io"
_ATTRIBUTION_META_KEY = "created_with"
_ATTRIBUTION_META_VALUE = "w3ir.io"


def attribution_enabled() -> bool:
    """Чи додавати attribution у бандл (дефолт — увімкнено).

    Вимикається рівно значенням ``EXPORT_ATTRIBUTION="0"`` (для платних тарифів,
    як free-watermark Canva/Notion). Читається ліниво — у момент виклику, після
    ``load_dotenv`` (як інші env-перемикачі в services), не як module-level константа.
    """
    return os.getenv("EXPORT_ATTRIBUTION", "1") != "0"

# chain "base" → ERC-721, "solana" → Metaplex (для web3_service.build_token_metadata)
PLATFORMS: dict[str, dict] = {
    "opensea": {
        "label": "OpenSea / ERC-721 (EVM)",
        "chain": "base",
        "start_index": 1,
        "img_dir": "images",
        "meta_dir": "metadata",
        "layout": "json",
    },
    "metaplex": {
        "label": "Metaplex / Candy Machine (Solana)",
        "chain": "solana",
        "start_index": 0,
        "img_dir": "assets",
        "meta_dir": "assets",
        "layout": "json",
    },
    "thirdweb": {
        "label": "thirdweb Batch Upload (EVM)",
        "chain": "base",
        "start_index": 0,
        "img_dir": "images",
        "meta_dir": "",
        "layout": "csv",
    },
    "generic": {
        "label": "Generic ZIP",
        "chain": "base",
        "start_index": 1,
        "img_dir": "images",
        "meta_dir": "metadata",
        "layout": "json",
    },
}


def _image_ext(item: dict) -> str:
    fn = str(item.get("filename") or "")
    return ".jpg" if fn.lower().endswith((".jpg", ".jpeg")) else ".png"


def _token_name(collection_name: str, number: int, item: dict) -> str:
    # Продукт EN: назва токена гарантовано без кирилиці (to_product_en → translit-фолбек).
    if collection_name:
        return f"{to_product_en(collection_name)} #{number}"
    return str(to_product_en(item.get("name")) if item.get("name") else f"#{number}")


def _build_metadata(
    platform: str, item: dict, image_field: str, number: int, collection_name: str,
    *, symbol: str = "", royalty_bps: int = 500, creator: str = "",
) -> dict:
    """Метадані одного токена під стандарт платформи (ERC-721 або Metaplex)."""
    spec = PLATFORMS[platform]
    src = {**item, "name": _token_name(collection_name, number, item), "image_uri": image_field}
    return web3_service.build_token_metadata(
        spec["chain"], src, symbol=symbol, royalty_bps=royalty_bps, creator=creator,
    )


def _ordered(assets: list[dict]) -> list[dict]:
    """Копія активів із порахованими rarity-ранками (для provenance-атрибутів)."""
    rows = [dict(a) for a in assets]
    if len(rows) > 1 and any(r.get("traits") for r in rows):
        add_rarity_ranks(rows)
    return rows


def validate_export_assets(
    assets: list[dict],
    *,
    min_curator_rating: int = 0,
    min_image_bytes: int = 64,
) -> tuple[list[tuple[str, int | None]], list[tuple[str, int | None]]]:
    """Перевірка перед експортом. Повертає (errors, warnings) — коди для i18n + індекс токена (1-based)."""
    from pathlib import Path

    errors: list[tuple[str, int | None]] = []
    warnings: list[tuple[str, int | None]] = []
    if not assets:
        errors.append(("no_assets", None))
        return errors, warnings
    seen_prompts: dict[str, int] = {}
    for i, item in enumerate(assets, start=1):
        has_bytes = bool(item.get("image_bytes"))
        path = str(item.get("path") or "")
        has_path = bool(path)
        if not has_bytes and not has_path:
            errors.append(("missing_image", i))
        elif has_bytes and len(item.get("image_bytes") or b"") < min_image_bytes:
            errors.append(("corrupt_image", i))
        elif has_path:
            try:
                if Path(path).stat().st_size < min_image_bytes:
                    errors.append(("corrupt_image", i))
            except OSError:
                errors.append(("missing_image", i))
        rating = int(item.get("curator_rating") or 0)
        if min_curator_rating > 0 and rating < min_curator_rating:
            errors.append(("low_curator_rating", i))
        if not (item.get("description") or item.get("prompt") or "").strip():
            warnings.append(("empty_description", i))
        norm = " ".join(str(item.get("prompt") or "").lower().split())
        if norm:
            if norm in seen_prompts:
                warnings.append(("duplicate_prompt", i))
            else:
                seen_prompts[norm] = i
        name = str(item.get("name") or "")
        if len(name) > 32:
            warnings.append(("name_too_long", i))
        if _has_cyrillic(item):
            warnings.append(("non_english", i))
    return errors, warnings


_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def _has_cyrillic(item: dict) -> bool:
    """Чи є кирилиця у полях айтема, що течуть у метадані (traits/name/description/prompt).

    Сигнал для UI: продукт EN-only, тож такі значення буде транслітеровано
    (to_product_en) на експорті. Провенанс/движки — EN за побудовою, не скануємо.
    """
    parts = [str(item.get("name") or ""), str(item.get("description") or ""),
             str(item.get("prompt") or "")]
    for k, v in (item.get("traits") or {}).items():
        parts.append(str(k))
        parts.append(str(v))
    return any(_CYRILLIC.search(p) for p in parts)


def _thirdweb_csv(metadata: list[dict], image_names: list[str]) -> str:
    """CSV для thirdweb «Batch Upload»: name, description, image + колонки атрибутів.

    Колонки трейтів беруться з attributes зібраних метаданих (включно з Prompt-Lock
    і provenance) — thirdweb трактує зайві колонки як attributes токена.
    """
    trait_types: list[str] = []
    for meta in metadata:
        for attr in meta.get("attributes", []):
            tt = attr.get("trait_type")
            if tt and tt not in trait_types:
                trait_types.append(tt)
    header = ["name", "description", "image", *trait_types]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for meta, img in zip(metadata, image_names):
        values = {a.get("trait_type"): a.get("value", "") for a in meta.get("attributes", [])}
        w.writerow([meta.get("name", ""), meta.get("description", ""), img,
                    *[values.get(tt, "") for tt in trait_types]])
    return buf.getvalue()


def _attribution_line() -> str | None:
    if attribution_enabled():
        return f"{ATTRIBUTION_TEXT} — {ATTRIBUTION_URL}"
    return None


def _filenames(platform: str, rows: list[dict]) -> tuple[list[str], list[int]]:
    """Імена файлів зображень і номери токенів за індексацією платформи."""
    spec = PLATFORMS[platform]
    start = spec["start_index"]
    names, numbers = [], []
    for i, item in enumerate(rows):
        idx = start + i
        names.append(f"{idx}{_image_ext(item)}")
        numbers.append(idx)
    return names, numbers


def build_metadata_list(
    platform: str, assets: list[dict], collection_name: str = "",
    *, image_base_uri: str = "", symbol: str = "", royalty_bps: int = 500, creator: str = "",
) -> list[dict]:
    """Список метаданих усіх токенів під платформу. image = base/<file> або <file>."""
    rows = _ordered(assets)
    image_names, numbers = _filenames(platform, rows)
    base = image_base_uri.rstrip("/")
    # Metaplex/sugar строго валідує JSON-схему → top-level created_with туди НЕ кладемо
    # (attribution для Solana лишається в README). Для решти — безпечний зайвий ключ.
    add_attr = attribution_enabled() and platform != "metaplex"
    out = []
    for item, img_name, number in zip(rows, image_names, numbers):
        image_field = f"{base}/{img_name}" if base else img_name
        meta = _build_metadata(
            platform, item, image_field, number, collection_name,
            symbol=symbol, royalty_bps=royalty_bps, creator=creator,
        )
        if add_attr:
            meta[_ATTRIBUTION_META_KEY] = _ATTRIBUTION_META_VALUE
        out.append(meta)
    return out


def describe_bundle_structure(platform: str, n_assets: int, collection_name: str = "") -> list[str]:
    """Прев'ю структури майбутнього ZIP (рядки дерева) — чиста, без зборки архіву.

    Імена відображають реальну індексацію платформи (start_index/img_dir/meta_dir/
    layout) на прикладі першого й останнього токена з «…» між ними. Прозу (підписи)
    додає UI; тут — лише шляхи (мовно-нейтральні). Розширення для прикладу — .png.
    """
    n = max(int(n_assets), 0)

    if platform == "w3ir":
        root = f"{collection_name or 'collection'}{W3IR_PACKAGE_EXT}"
        if n == 0:
            return [root]
        last = n - 1
        lines = [
            root,
            "├─ items/item-0/manifest.json",
            "├─ items/item-0/mint-state.json",
            "├─ items/item-0/metadata.json",
            "├─ items/item-0/asset/0.png",
        ]
        if n > 1:
            lines.append("├─ …")
            lines.append(
                f"├─ items/item-{last}/ (manifest.json · mint-state.json · metadata.json · asset/{last}.png)"
            )
        lines.append("└─ batch-manifest.json")
        return lines

    if platform == "sugar":
        root = f"{collection_name or 'collection'}{CANDY_MACHINE_EXT}"
        if n == 0:
            return [root]
        last = n - 1
        png = "assets/0.png" if n == 1 else f"assets/0.png … {last}.png"
        meta = "assets/0.json" if n == 1 else f"assets/0.json … {last}.json"
        return [
            root,
            "├─ config.json",
            "├─ assets/collection.json",
            "├─ assets/collection.png",
            f"├─ {png}",
            f"├─ {meta}",
            "└─ README.txt",
        ]

    spec = PLATFORMS.get(platform)
    if spec is None:
        return []
    root = f"{collection_name or 'bundle'}-{platform}.zip"
    if n == 0:
        return [root]
    start = spec["start_index"]
    last = start + n - 1

    def _rng(suffix: str) -> str:
        return f"{start}{suffix}" if n == 1 else f"{start}{suffix} … {last}{suffix}"

    lines = [root, f"├─ {spec['img_dir']}/{_rng('.png')}"]
    if spec["layout"] == "csv":
        lines.append("├─ metadata.csv")
    else:
        meta_dir = spec["meta_dir"]
        prefix = f"{meta_dir}/" if meta_dir else ""
        lines.append(f"├─ {prefix}{_rng('.json')}")
        if platform != "metaplex":  # sugar не любить сторонніх файлів — collection.json не кладемо
            lines.append("├─ collection.json")
    lines.append("└─ README.txt")
    return lines


def ipfs_gateway_url(cid: str) -> str:
    """Публічний HTTPS-gateway для CID (Pinata)."""
    return f"https://gateway.pinata.cloud/ipfs/{cid}"


def ipfs_manifest_document(
    result: dict,
    *,
    collection_name: str = "",
    platform: str = "",
) -> dict:
    """Mint-ready довідка після Pinata — кладеться в ZIP як ipfs-manifest.json."""
    meta_cid = str(result.get("metadata_cid", ""))
    img_cid = str(result.get("images_cid", ""))
    return {
        "version": 1,
        "published_at": result.get("published_at") or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "collection_name": collection_name,
        "platform": platform,
        "token_count": int(result.get("count", 0)),
        "base_uri": result.get("base_uri", ""),
        "image_base_uri": result.get("image_base_uri", ""),
        "metadata_cid": meta_cid,
        "images_cid": img_cid,
        "gateway_metadata": ipfs_gateway_url(meta_cid) if meta_cid else "",
        "gateway_images": ipfs_gateway_url(img_cid) if img_cid else "",
        "mint_hint": "EVM Drop: вставте base_uri в Base URI контракту. Token URI = base_uri + <n>.json",
    }


def build_zip(
    platform: str, assets: list[dict], collection_name: str = "",
    *, image_base_uri: str = "", symbol: str = "", royalty_bps: int = 500, creator: str = "",
    ipfs_result: dict | None = None, lang: str = "en",
) -> bytes:
    """ZIP-бандл під платформу. Зображення беруться з item['image_bytes'] (якщо є).

    Якщо передано `ipfs_result` (після Pinata) — metadata в ZIP містить ті самі
    `ipfs://` посилання, що на ланцюгу, плюс `ipfs-manifest.json` з baseURI.
    """
    if platform not in PLATFORMS:
        raise ValueError(f"Невідома платформа: {platform}")
    spec = PLATFORMS[platform]
    rows = _ordered(assets)
    image_names, numbers = _filenames(platform, rows)
    effective_image_base = (ipfs_result or {}).get("image_base_uri") or image_base_uri
    metadata = build_metadata_list(
        platform, assets, collection_name,
        image_base_uri=effective_image_base, symbol=symbol, royalty_bps=royalty_bps, creator=creator,
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # зображення
        for item, img_name in zip(rows, image_names):
            data = item.get("image_bytes")
            if data:
                zf.writestr(f"{spec['img_dir']}/{img_name}", data)
        # метадані
        if spec["layout"] == "csv":
            zf.writestr("metadata.csv", _thirdweb_csv(metadata, image_names))
        else:
            meta_dir = spec["meta_dir"]
            for meta, number in zip(metadata, numbers):
                path = f"{meta_dir}/{number}.json" if meta_dir else f"{number}.json"
                zf.writestr(path, json.dumps(meta, ensure_ascii=False, indent=2))
            if platform != "metaplex":  # sugar не любить сторонніх файлів у assets/
                zf.writestr("collection.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        if ipfs_result:
            zf.writestr(
                "ipfs-manifest.json",
                json.dumps(
                    ipfs_manifest_document(ipfs_result, collection_name=collection_name, platform=platform),
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        zf.writestr(
            "README.txt",
            zip_readme(
                platform, lang, ipfs_result=ipfs_result, attribution_line=_attribution_line(),
            ),
        )
    return buf.getvalue()


def ipfs_publish(
    platform: str, assets: list[dict], jwt: str, collection_name: str = "",
    *, symbol: str = "", royalty_bps: int = 500, creator: str = "", uploader=None,
) -> dict:
    """Відвантажує images/ та metadata/ як IPFS-папки. Повертає CID-и та baseURI.

    Метадані будуються з image = ipfs://<images_cid>/<file> — одразу mint-ready.

    uploader: опційний callable (files, pin_name) -> cid — напр.
    `PinataService.pin_directory` для захисної обробки 429/timeout. За замовч.
    — пряме `ipfs.upload_directory` з переданим jwt.
    """
    upload = uploader or (lambda files, name: ipfs.upload_directory(jwt, files, name))
    rows = _ordered(assets)
    image_names, numbers = _filenames(platform, rows)

    image_files = [
        (img_name, item["image_bytes"])
        for item, img_name in zip(rows, image_names)
        if item.get("image_bytes")
    ]
    if not image_files:
        raise ValueError("Немає зображень для відвантаження в IPFS.")
    images_cid = upload(image_files, f"{collection_name or 'bundle'}-images")

    metadata = build_metadata_list(
        platform, assets, collection_name,
        image_base_uri=f"ipfs://{images_cid}", symbol=symbol, royalty_bps=royalty_bps, creator=creator,
    )
    meta_files = [
        (f"{number}.json", json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"))
        for meta, number in zip(metadata, numbers)
    ]
    metadata_cid = upload(meta_files, f"{collection_name or 'bundle'}-metadata")

    return {
        "images_cid": images_cid,
        "metadata_cid": metadata_cid,
        "base_uri": f"ipfs://{metadata_cid}/",
        "image_base_uri": f"ipfs://{images_cid}/",
        "count": len(meta_files),
        "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


# ── Профіль «W3IR Platform» (B8) ──────────────────────────────────────────────
# Окремий від PLATFORMS контейнер: бандл, який ПРЯМО імпортується у W3IR-платформу
# (C:\Web3) одним кроком, закриваючи «мінт відкладено» без контрактів у нас.
# Контракт відтворено з frontend/src/lib/nft-package/{types,import}.ts (див.
# B8_АНАЛІЗ_БАНДЛА.md). Імпорт читає лише manifest.json + mint-state.json + asset/;
# metadata.json — офлайн-прев'ю, платформа його ігнорує й перебудовує при мінті.

W3IR_PACKAGE_VERSION = 1
W3IR_PACKAGE_EXT = ".w3ir-nft.zip"


def _w3ir_traits(item: dict) -> list[dict]:
    """Трейти у форматі платформи: масив {trait_type, value} (ключі перекладено EN).

    Лише користувацькі генеративні трейти. Провенанс (rarity/curator) свідомо НЕ
    кладемо у mint-state: він унікальний на токен (засмічує trait-частоти маркетплейсу)
    і рахується проти ліміту 20 атрибутів; AI-провенанс несе aiMeta, повний — metadata.json.
    """
    return [
        {"trait_type": trait_type_en(str(k)), "value": to_product_en(str(v))}
        for k, v in (item.get("traits") or {}).items()
        if str(k).strip() and str(v).strip()
    ]


def _w3ir_ai_meta(item: dict) -> dict | None:
    """aiMeta для mint-state. None, якщо нема prompt+model — їх імпорт інакше відкине aiMeta.

    Платформа при імпорті лишає лише {prompt, model, style, seed} (promptHash/recipe
    відкидаються в sanitizeMintState), тож більше не кладемо.
    """
    prompt = str(item.get("prompt") or "").strip()
    model = str(item.get("engine") or "").strip()
    if not (prompt and model):
        return None
    seed = item.get("seed")
    style = str(item.get("style") or "").strip()
    return {
        "prompt": to_product_en(prompt),
        "model": model,
        "style": to_product_en(style) or None,
        "seed": seed if isinstance(seed, int) else 0,
    }


def build_w3ir_package_zip(
    assets: list[dict], collection_name: str = "", *, lang: str = "en",
) -> bytes:
    """ZIP у форматі W3IR-платформи (`.w3ir-nft.zip`) — прямий імпорт у мінт-конструктор.

    Кожен токен — окрема папка `items/item-<i>/` з manifest.json (version=1, mediaKind,
    mime, assetFile), mint-state.json (name/description/traits[]/aiMeta), metadata.json
    (офлайн-прев'ю) та asset/<file>. Корінь — batch-manifest.json. Зображення беруться
    з `item['image_bytes']`; айтеми без байтів пропускаються.
    """
    rows = [r for r in _ordered(assets) if r.get("image_bytes")]
    if not rows:
        raise ValueError("Немає зображень для пакета W3IR Platform.")

    exported_at = datetime.now(timezone.utc).isoformat()
    folders: list[str] = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, item in enumerate(rows):
            folder = f"items/item-{i}"
            folders.append(folder)
            ext = _image_ext(item)
            asset_file = f"{i}{ext}"
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
            name = _token_name(collection_name, i + 1, item)
            description = to_product_en(str(item.get("description") or item.get("prompt") or ""))

            manifest = {
                "version": W3IR_PACKAGE_VERSION,
                "exportedAt": exported_at,
                "mediaKind": "image",
                "mime": mime,
                "assetFile": asset_file,
            }
            mint_state = {
                "name": name,
                "description": description,
                "traits": _w3ir_traits(item),
                "aiMeta": _w3ir_ai_meta(item),
                "mediaKind": "image",
            }
            # Офлайн-прев'ю метаданих (повний ERC-721 із provenance); імпорт ігнорує.
            preview = web3_service.build_erc721_metadata(
                name, description, f"asset/{asset_file}",
                item.get("traits", {}), prompt=str(item.get("prompt") or ""), item=item,
            )

            zf.writestr(f"{folder}/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr(f"{folder}/mint-state.json", json.dumps(mint_state, ensure_ascii=False, indent=2))
            zf.writestr(f"{folder}/metadata.json", json.dumps(preview, ensure_ascii=False, indent=2))
            zf.writestr(f"{folder}/asset/{asset_file}", item["image_bytes"])

        batch_manifest = {
            "version": W3IR_PACKAGE_VERSION,
            "exportedAt": exported_at,
            "itemCount": len(rows),
            "folders": folders,
        }
        zf.writestr("batch-manifest.json", json.dumps(batch_manifest, ensure_ascii=False, indent=2))
        zf.writestr(
            "README.txt",
            zip_readme("w3ir", lang, attribution_line=_attribution_line()),
        )
    return buf.getvalue()


# ── Профіль «Candy Machine / Sugar-ready» (B9) ────────────────────────────────
# Окремий від PLATFORMS контейнер: готова тека під `sugar deploy` (Metaplex CLI).
# Промт лишається producer'ом — підпис і деплой роблять гаманцем користувача;
# жодних ключів на сервері. assets/ переюзає метадані профілю metaplex
# (Sugar сам завантажує файли при deploy → image="<i>.png", не ipfs://).
# Деталі/landmines — у відповіді проєктування (B9).

CANDY_MACHINE_EXT = "-candy-machine.zip"


@dataclass
class CandyGuards:
    """Налаштування Candy Machine guards (мапиться у config.json → guards.default).

    allowlist НЕ перетворюється на merkleRoot тут (потребує JS-тулінгу) — лише
    пишеться окремим allowlist.json, а guard додається кроком `sugar guard add`.
    """

    price_sol: float | None = None
    treasury: str = ""            # destination для solPayment (обов'язк., якщо price_sol)
    start_date: str | None = None  # ISO-8601, напр. "2026-07-01T16:00:00Z"
    end_date: str | None = None
    mint_limit: int | None = None  # ліміт мінтів на гаманець
    allowlist: list[str] | None = None
    bot_tax_sol: float = 0.01      # антибот-податок (безпечний дефолт)

    def to_guard_config(self) -> dict:
        """guards-блок Sugar. solPayment без treasury — помилка (інакше невалідний guard)."""
        default: dict = {}
        if self.bot_tax_sol and self.bot_tax_sol > 0:
            default["botTax"] = {"value": float(self.bot_tax_sol), "lastInstruction": True}
        if self.price_sol is not None and self.price_sol > 0:
            dest = (self.treasury or "").strip()
            if not dest:
                raise ValueError("solPayment потребує treasury (адресу призначення SOL).")
            default["solPayment"] = {"value": float(self.price_sol), "destination": dest}
        if self.start_date:
            default["startDate"] = {"date": self.start_date}
        if self.end_date:
            default["endDate"] = {"date": self.end_date}
        if self.mint_limit is not None and int(self.mint_limit) > 0:
            default["mintLimit"] = {"id": 1, "limit": int(self.mint_limit)}
        return {"default": default, "groups": None}


def build_candy_machine_config(
    n: int, *, symbol: str = "", royalty_bps: int = 500, creator: str = "",
    guards: CandyGuards | None = None,
) -> dict:
    """config.json для Sugar. uploadMethod=bundlr (0 секретів у бандлі — див. landmine).

    creator обов'язковий (Solana base58 pubkey; не lower-кейсимо) — share=100.
    PINATA_JWT свідомо НЕ вписуємо: завантажуваний бандл не повинен нести секрет.
    """
    creator = (creator or "").strip()
    if not creator:
        raise ValueError("Candy Machine потребує адресу creator (Solana pubkey).")
    guards = guards or CandyGuards()
    return {
        "number": int(n),
        "symbol": symbol[:web3_service.METAPLEX_SYMBOL_LIMIT],
        "sellerFeeBasisPoints": int(royalty_bps),
        "isMutable": True,
        "isSequential": False,
        "creators": [{"address": creator, "share": 100}],
        "uploadMethod": "bundlr",
        "awsConfig": None,
        "nftStorageAuthToken": None,
        "pinataConfig": None,
        "hiddenSettings": None,
        "guards": guards.to_guard_config(),
    }


def build_candy_machine_package_zip(
    assets: list[dict], collection_name: str = "", *,
    symbol: str = "", royalty_bps: int = 500, creator: str = "",
    guards: CandyGuards | None = None, collection_image: bytes | None = None,
    lang: str = "en",
) -> bytes:
    """ZIP «Candy Machine / Sugar-ready»: assets/ (токени + collection) + config.json.

    Переюзає метадані профілю metaplex (image="<i>.png" — Sugar завантажить сам).
    collection.png/json — окремий parent-NFT (не входить у number). Айтеми без
    image_bytes пропускаються; creator (Solana pubkey) обов'язковий.
    """
    guards = guards or CandyGuards()
    rows = [r for r in _ordered(assets) if r.get("image_bytes")]
    if not rows:
        raise ValueError("Немає зображень для пакета Candy Machine.")
    creator = (creator or "").strip()
    if not creator:
        raise ValueError("Candy Machine потребує адресу creator (Solana pubkey).")

    metadata = build_metadata_list(
        "metaplex", rows, collection_name,
        symbol=symbol, royalty_bps=royalty_bps, creator=creator,
    )
    image_names, numbers = _filenames("metaplex", rows)
    config = build_candy_machine_config(
        len(rows), symbol=symbol, royalty_bps=royalty_bps, creator=creator, guards=guards,
    )
    cover = collection_image or rows[0]["image_bytes"]
    collection_meta = web3_service.build_metaplex_metadata(
        collection_name or "Collection", symbol,
        f"{collection_name or 'Collection'} — generated with w3ir.io",
        "collection.png", {}, royalty_bps=royalty_bps, creator=creator,
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item, img_name in zip(rows, image_names):
            zf.writestr(f"assets/{img_name}", item["image_bytes"])
        for meta, number in zip(metadata, numbers):
            zf.writestr(f"assets/{number}.json", json.dumps(meta, ensure_ascii=False, indent=2))
        # колекційний parent-NFT (Sugar очікує collection.png/json саме в assets/)
        zf.writestr("assets/collection.png", cover)
        zf.writestr("assets/collection.json", json.dumps(collection_meta, ensure_ascii=False, indent=2))
        zf.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))
        if guards.allowlist:
            zf.writestr("allowlist.json", json.dumps(list(guards.allowlist), ensure_ascii=False, indent=2))
        zf.writestr(
            "README.txt",
            zip_readme(
                "sugar",
                lang,
                has_allowlist=bool(guards.allowlist),
                attribution_line=_attribution_line(),
            ),
        )
    return buf.getvalue()
