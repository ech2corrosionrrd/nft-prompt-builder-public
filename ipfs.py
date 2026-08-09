"""Завантаження зображень і метаданих в IPFS через Pinata (pinFileToIPFS)."""

import json
import os
import re
from pathlib import Path

import httpx

import network_config

PINATA_PIN_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
TIMEOUT_SECONDS = 300.0

_MIME = {
    "png": "image/png",
    "json": "application/json",
}


def get_pinata_jwt() -> str | None:
    return os.environ.get("PINATA_JWT") or None


def platform_pinata_eligible(wallet: str) -> bool:
    """Чи можна пінити через спільний Pinata W3IR (лише поповнені/grant гаманці)."""
    if not get_pinata_jwt():
        return False
    from services import freemium  # lazy — уникаємо циклів на імпорті модуля

    return freemium.is_exempt(wallet)


def resolve_upload_jwt(wallet: str, mode: str, user_jwt: str = "") -> str | None:
    """JWT для IPFS-аплоуду: platform | own. None — немає валідного ключа."""
    if mode == "platform":
        jwt = get_pinata_jwt()
        if jwt and platform_pinata_eligible(wallet):
            return jwt
        return None
    return (user_jwt or "").strip() or None


def collect_directory_files(folder: Path, dir_name: str) -> list[tuple[str, bytes]]:
    """Збирає PNG/JSON-файли папки як (шлях_у_каталозі, вміст)."""
    files = []
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower().lstrip(".") in _MIME:
            files.append((f"{dir_name}/{path.name}", path.read_bytes()))
    return files


def metadata_files(metadata: list[dict], dir_name: str) -> list[tuple[str, bytes]]:
    """Перетворює список метаданих на файли <token_id>.json для каталогу IPFS."""
    files = []
    for meta in metadata:
        token_id = str(meta.get("token_id") or meta["name"].rsplit("#", 1)[-1].strip())
        clean = {k: v for k, v in meta.items() if k != "token_id"}
        files.append((
            f"{dir_name}/{token_id}.json",
            json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8"),
        ))
    return files


def extract_cid(response_json: dict) -> str:
    cid = response_json.get("IpfsHash", "")
    if not cid:
        raise ValueError(f"Pinata не повернула CID: {response_json}")
    return cid


def _folder_name_from_pin(pin_name: str) -> str:
    """Безпечна назва кореневої IPFS-папки з pin_name (метадані Pinata)."""
    name = (pin_name or "files").strip().replace("\\", "/")
    name = name.split("/")[-1] or "files"
    safe = re.sub(r"[^\w\-.]+", "-", name).strip("-") or "files"
    return safe[:64]


def _directory_upload_paths(
    files: list[tuple[str, bytes]], pin_name: str,
) -> list[tuple[str, bytes]]:
    """Pinata приймає кілька file-parts лише як один каталог — усі шляхи
    мають спільний кореневий сегмент (``folder/file.ext``). Інакше HTTP 400:
    «More than one file and/or directory was provided for pinning».
    """
    if len(files) <= 1:
        return files
    normalized = [(p.replace("\\", "/").lstrip("/"), c) for p, c in files]
    roots = {p.split("/")[0] for p, _ in normalized if p}
    if len(roots) == 1 and all("/" in p for p, _ in normalized):
        return normalized
    folder = _folder_name_from_pin(pin_name)
    out: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for path, content in normalized:
        base = path.split("/")[-1] or "file"
        key = base if base not in seen else path.replace("/", "_")
        seen.add(key)
        out.append((f"{folder}/{key}", content))
    return out


def upload_file(jwt: str, filename: str, content: bytes, pin_name: str) -> str:
    """Завантажує один файл у Pinata. Повертає CID файлу (URI: ipfs://<CID>)."""
    mime = _MIME.get(filename.rsplit(".", 1)[-1].lower(), "application/octet-stream")
    response = httpx.post(
        PINATA_PIN_URL,
        headers=network_config.web3_headers({"Authorization": f"Bearer {jwt}"}),
        files=[("file", (filename, content, mime))],
        data={"pinataMetadata": json.dumps({"name": pin_name})},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return extract_cid(response.json())


def upload_directory(jwt: str, files: list[tuple[str, bytes]], pin_name: str) -> str:
    """Завантажує файли як IPFS-каталог. Повертає CID каталогу.

    Файли йдуть зі спільним префіксом (наприклад, «images/1.png»), тому Pinata
    створює каталог, а доступ до файлів — ipfs://<CID>/<ім'я файлу>.
    """
    if not files:
        raise ValueError("Немає файлів для завантаження в IPFS")

    files = _directory_upload_paths(files, pin_name)
    multipart = [
        (
            "file",
            (path, content, _MIME.get(path.rsplit(".", 1)[-1].lower(), "application/octet-stream")),
        )
        for path, content in files
    ]
    response = httpx.post(
        PINATA_PIN_URL,
        headers=network_config.web3_headers({"Authorization": f"Bearer {jwt}"}),
        files=multipart,
        data={"pinataMetadata": json.dumps({"name": pin_name})},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return extract_cid(response.json())
