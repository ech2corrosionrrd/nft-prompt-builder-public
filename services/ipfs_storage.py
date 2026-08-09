"""PinataService — high-level обгортка над наявним `ipfs.py` із захисною логікою.

НЕ дублює HTTP: пінінг делегується в `ipfs.upload_directory` (перевірений
multipart на api.pinata.cloud). Цей шар додає:
  • валідацію JWT,
  • backoff-ретрай на 429 (rate-limit) і мапінг timeout/auth/з'єднання
    у зрозумілі винятки,
  • disk-based двостадійний `publish_collection`: картинки → images_cid,
    переписані локальні JSON (image=ipfs://images_cid/<file>) → metadata_cid.

In-memory шлях конвеєра використовує `export_bundle.ipfs_publish`, який може
приймати `uploader=PinataService.pin_directory` для тієї ж обробки помилок.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import httpx

import ipfs

_IMAGE_EXTS = (".png", ".jpg", ".jpeg")


class PinataError(Exception):
    """Базова помилка пінінгу."""


class PinataAuthError(PinataError):
    """JWT відсутній або відхилений (401/403)."""


class PinataRateLimitError(PinataError):
    """Pinata повертає 429 і після ретраїв — ліміт запитів не знято."""


class PinataTimeoutError(PinataError):
    """Таймаут з'єднання/відповіді Pinata."""


class PinataService:
    """Тонка обгортка над `ipfs.upload_directory`, прив'язана до одного JWT.

    max_retries / backoff_base керують експоненційним backoff на 429
    (затримки: base, base*2, base*4, …). `_sleep` винесено для тестів.
    """

    def __init__(self, jwt_token: str, *, max_retries: int = 3, backoff_base: float = 1.0) -> None:
        token = (jwt_token or "").strip()
        if not token:
            raise PinataAuthError("PINATA_JWT відсутній — вкажіть токен Pinata.")
        self._jwt = token
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = time.sleep  # підміняється в тестах

    # ── Примітив: пінінг папки з ретраєм на 429 ──────────────────────────────────
    def pin_directory(self, files: list[tuple[str, bytes]], pin_name: str) -> str:
        """Пінить файли як IPFS-папку → CID. Ретрай на 429; мапінг інших збоїв."""
        if not files:
            raise PinataError("Немає файлів для завантаження в IPFS.")
        attempt = 0
        while True:
            try:
                return ipfs.upload_directory(self._jwt, files, pin_name)
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code == 429:
                    if attempt < self._max_retries:
                        self._sleep(self._backoff_base * (2 ** attempt))
                        attempt += 1
                        continue
                    raise PinataRateLimitError(
                        f"Pinata: ліміт запитів (429) не знято після {self._max_retries} спроб."
                    ) from exc
                if code in (401, 403):
                    raise PinataAuthError(
                        f"Pinata відхилила JWT ({code}). Перевірте PINATA_JWT."
                    ) from exc
                body = (exc.response.text or "")[:200]
                raise PinataError(f"Pinata HTTP {code}: {body}") from exc
            except httpx.TimeoutException as exc:
                raise PinataTimeoutError(
                    "Таймаут з'єднання з Pinata — велика колекція або повільна мережа."
                ) from exc
            except httpx.RequestError as exc:
                raise PinataError(f"Помилка з'єднання з Pinata: {exc}") from exc

    # ── Двостадійний disk-деплой ─────────────────────────────────────────────────
    def publish_collection(
        self,
        images_dir: str | Path,
        metadata_dir: str | Path,
        *,
        collection_name: str = "",
        default_ext: str = ".png",
    ) -> str:
        """Stage 1: пін картинок → images_cid.
        Stage 2: для кожного локального JSON виставити "image"=ipfs://images_cid/<file>,
        зберегти у temp-папку, запінити її → повернути metadata_cid (str).

        Імена зіставляються за stem (1.json ↔ 1.png/1.jpg).
        """
        images_dir, metadata_dir = Path(images_dir), Path(metadata_dir)

        # Stage 1 — картинки (ім'я без префікса → доступ ipfs://cid/<file>)
        img_paths = sorted(
            p for p in images_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
        )
        if not img_paths:
            raise PinataError(f"У {images_dir} немає зображень ({', '.join(_IMAGE_EXTS)}).")
        stem_to_image = {p.stem: p.name for p in img_paths}
        image_files = [(p.name, p.read_bytes()) for p in img_paths]
        images_cid = self.pin_directory(image_files, f"{collection_name or 'bundle'}-images")

        # Stage 2 — переписати image у локальних JSON, зберегти в temp, запінити папку
        json_paths = sorted(metadata_dir.glob("*.json"))
        if not json_paths:
            raise PinataError(f"У {metadata_dir} немає JSON-метаданих.")
        with tempfile.TemporaryDirectory(prefix="pinata-meta-") as td:
            tmp = Path(td)
            for jp in json_paths:
                try:
                    obj = json.loads(jp.read_text(encoding="utf-8"))
                except (ValueError, OSError) as exc:
                    raise PinataError(f"Не вдалося прочитати {jp.name}: {exc}") from exc
                image_name = stem_to_image.get(jp.stem, f"{jp.stem}{default_ext}")
                obj["image"] = f"ipfs://{images_cid}/{image_name}"
                (tmp / jp.name).write_text(
                    json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            meta_files = [(p.name, p.read_bytes()) for p in sorted(tmp.glob("*.json"))]
            metadata_cid = self.pin_directory(meta_files, f"{collection_name or 'bundle'}-metadata")
        return metadata_cid
