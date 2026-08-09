"""Етап 3 (Експорт): Export Center + опційний мінт через Thirdweb або Crossmint.

Вхід: st.session_state[APPROVED_CONTENT] (Етап 2) АБО Точка входу 3 —
завантаження власних JPG/PNG через st.file_uploader.
"""

from pathlib import Path

import streamlit as st

import ipfs
import network_config
from metadata_provenance import add_rarity_ranks
from services import public_gallery, web3_service
from state.pipeline_state import APPROVED_CONTENT, MINT_ASSETS, ensure_mint_queue_from_approved
from ui import billing_ui, export_center
from ui_strings import t


def collection_name_warnings(name: str) -> list[str]:
    """Коди попереджень для назви колекції (EN metadata)."""
    if not name or not name.strip():
        return []
    out: list[str] = []
    if any(ord(c) > 127 for c in name):
        out.append("non_ascii")
    if name != name.strip() or "  " in name:
        out.append("spaces")
    return out


def _render_collection_name_field() -> str:
    collection_name = st.text_input(
        t("pl3.coll_name"),
        key="pl3_coll_name",
        placeholder=t("pl3.coll_name_ph"),
        help=t("pl3.coll_name_help"),
    )
    if not collection_name.strip():
        st.caption(t("pl3.coll_name_hint"))
    else:
        for code in collection_name_warnings(collection_name):
            if code == "non_ascii":
                st.warning(t("pl3.coll_name_warn_non_ascii"))
            elif code == "spaces":
                st.warning(t("pl3.coll_name_warn_spaces"))
    return collection_name


def _load_assets() -> None:
    """Формує чергу мінтингу з approved_content або завантажених файлів."""
    approved = st.session_state.get(APPROVED_CONTENT, [])
    if approved:
        st.info(t("pl3.from_stage2", n=len(approved)))
        if st.button(t("pl3.take_approved"), width='stretch', key="pl3_take_approved"):
            st.session_state[MINT_ASSETS] = [dict(item) for item in approved]
            st.rerun()

    with st.expander(t("pl3.upload_expand"), expanded=not approved):
        uploads = st.file_uploader(
            t("pl3.upload_label"), type=["png", "jpg", "jpeg"],
            accept_multiple_files=True, key="pl3_uploads",
        )
        if uploads and st.button(t("pl3.take_uploads", n=len(uploads)), width='stretch', key="pl3_take_uploads"):
            # завантаження одразу на диск (temp_assets/<uuid>) — не тримаємо в пам'яті
            st.session_state[MINT_ASSETS] = [
                {
                    "name": up.name.rsplit(".", 1)[0],
                    "description": "",
                    "prompt": "",
                    "traits": {},
                    "path": str(network_config.save_temp_asset(
                        up.getvalue(),
                        suffix=".jpg" if up.name.lower().endswith((".jpg", ".jpeg")) else ".png",
                    )),
                    "filename": up.name,
                }
                for up in uploads
            ]
            st.rerun()


def _pin_all(jwt: str, assets: list[dict], chain: str, collection_name: str,
             symbol: str, royalty_bps: int, creator: str,
             collection_id: str = "", reveal_mode: bool = False) -> None:
    if len(assets) > 1 and any(a.get("traits") for a in assets):
        add_rarity_ranks(assets)
    placeholder = f"{network_config.get_app_url()}/app/static/unrevealed.png"
    progress = st.progress(0, text=t("pl3.mint.ipfs_progress"))
    errors = []
    for i, item in enumerate(assets):
        progress.progress(
            i / len(assets),
            text=t("pl3.mint.asset_progress", i=i + 1, total=len(assets)),
        )
        try:
            item["name"] = f"{collection_name} #{i + 1}" if collection_name else item["name"]
            if collection_id:
                item["collection_id"] = collection_id
            image_bytes = network_config.read_asset(item["path"])
            item["image_uri"] = web3_service.pin_asset(
                jwt, image_bytes, item.get("filename", f"{i + 1}.png"), f"pipeline-img-{i + 1}",
            )
            if reveal_mode:
                item["revealed_image_uri"] = item["image_uri"]
                item["reveal_status"] = "Unrevealed"
                meta_image = placeholder
            else:
                meta_image = item["image_uri"]
            item["metadata"] = web3_service.build_token_metadata(
                chain, {**item, "image_uri": meta_image},
                symbol=symbol, royalty_bps=royalty_bps, creator=creator,
            )
            item["token_uri"] = web3_service.pin_metadata(jwt, item["metadata"], f"pipeline-meta-{i + 1}")
        except Exception as e:
            errors.append(f"#{i + 1}: {e}")
    progress.empty()
    st.session_state[MINT_ASSETS] = assets
    if errors:
        st.warning(t("pl3.mint.pack_errors", n=len(errors), first=errors[0]))
    else:
        st.success(t("pl3.mint.pack_ok", n=len(assets)))


def render() -> None:
    st.markdown(t("pl3.title"))
    ensure_mint_queue_from_approved()
    _load_assets()

    assets = st.session_state.get(MINT_ASSETS, [])
    if not assets:
        st.warning(t("pl3.queue_empty"))
        return

    st.divider()
    st.markdown(t("pl3.queue_count", n=len(assets)))
    collection_name = _render_collection_name_field()

    export_center.render(assets, collection_name)

    st.divider()
    _render_share(assets, collection_name)

    st.divider()
    with st.expander(t("pl3.advanced_mint"), expanded=False):
        _render_mint(assets, collection_name)

    _render_results(assets)


def _share_images(assets: list[dict]) -> list[tuple[str, bytes]]:
    """Зчитує байти зображень черги для публікації вітрини (з temp-файлів на диску)."""
    out = []
    for i, a in enumerate(assets, start=1):
        path = a.get("path")
        if not path:
            continue
        try:
            data = network_config.read_asset(path)
        except OSError:
            continue
        ext = Path(path).suffix.lower() or ".png"
        out.append((f"{i}{ext}", data))
    return out


def _render_share(assets: list[dict], collection_name: str) -> None:
    """Публікація публічної shareable-вітрини колекції (G3.2)."""
    st.markdown(t("pl3.share.title"))
    st.caption(t("pl3.share.caption"))
    if st.button(t("pl3.share.button"), width='stretch', key="pl3_share"):
        images = _share_images(assets)
        if not images:
            st.warning(t("pl3.share.empty"))
        else:
            slug = public_gallery.publish_collection(
                collection_name or "Untitled collection", images,
                wallet=billing_ui.connected_wallet(),
            )
            st.session_state["pl3_share_url"] = f"https://w3ir.io/c/{slug}"
    url = st.session_state.get("pl3_share_url")
    if url:
        st.success(t("pl3.share.done"))
        st.code(url, language="text")  # вбудована кнопка копіювання
        st.link_button(t("pl3.share.open"), url, width='stretch')


def _render_mint(assets: list[dict], collection_name: str) -> None:
    with st.expander(t("pl3.mint.public_links_title"), expanded=False):
        st.caption(t("pl3.mint.public_links_caption", app_url=network_config.get_app_url()))
        if st.button(t("pl3.mint.public_links_btn"), width='stretch', key="pl3_publish"):
            errors = 0
            for item in assets:
                try:
                    item["public_url"] = network_config.publish_static_asset(item["path"])
                except OSError:
                    errors += 1
            st.session_state[MINT_ASSETS] = assets
            if errors:
                st.warning(t("pl3.mint.public_links_fail", n=errors))
        published = [a for a in assets if a.get("public_url")]
        if published:
            st.dataframe(
                [{t("pl3.mint.col_name"): a.get("name", ""), t("pl3.mint.col_url"): a["public_url"]} for a in published],
                width='stretch', hide_index=True,
            )

    s1, s2 = st.columns(2)
    with s1:
        chain_label = st.radio(t("pl3.mint.chain"), list(web3_service.CHAINS), key="pl3_chain")
        chain = web3_service.CHAINS[chain_label]
    with s2:
        engines = web3_service.ENGINES if chain == "base" else ["Crossmint API"]
        engine = st.radio(
            t("pl3.mint.engine"), engines, key="pl3_engine", help=t("pl3.mint.engine_help"),
        )

    collection_id = st.text_input(
        t("pl3.mint.coll_id"), key="pl3_coll_id",
        placeholder=t("pl3.mint.coll_id_ph"), help=t("pl3.mint.coll_id_help"),
    )
    reveal_mode = st.checkbox(
        t("pl3.mint.reveal"), key="pl3_reveal", help=t("pl3.mint.reveal_help"),
    )
    symbol, royalty_bps, creator = "", 500, ""
    if chain == "solana":
        m1, m2, m3 = st.columns(3)
        with m1:
            symbol = st.text_input(t("pl3.export.symbol"), max_chars=10, key="pl3_symbol", placeholder="APES")
        with m2:
            royalty_bps = int(st.number_input(t("pl3.export.royalty"), 0.0, 50.0, 5.0, 0.5, key="pl3_royalty") * 100)
        with m3:
            creator = st.text_input(
                t("pl3.export.creator"), key="pl3_creator", placeholder=t("pl3.mint.creator_ph"),
            )

    st.markdown(t("pl3.mint.step_a"))
    jwt = ipfs.get_pinata_jwt() or st.text_input(t("pl3.mint.pinata_jwt"), type="password", key="pl3_jwt")
    pinned = sum(1 for a in assets if a.get("token_uri"))
    if pinned:
        example_uri = next(a["token_uri"] for a in assets if a.get("token_uri"))
        st.caption(t("pl3.mint.pinned_caption", pinned=pinned, total=len(assets), example=example_uri))
    if st.button(t("pl3.mint.pin_all_btn"), width='stretch', key="pl3_pin", disabled=not jwt):
        _pin_all(jwt, assets, chain, collection_name, symbol, royalty_bps, creator, collection_id, reveal_mode)

    st.markdown(t("pl3.mint.step_b"))
    if engine == "Thirdweb SDK":
        if not web3_service._WEB3_AVAILABLE:
            st.error(t("pl3.mint.web3_missing"))
            return
        t1, t2 = st.columns(2)
        with t1:
            contract = st.text_input(t("pl3.mint.contract"), key="pl3_contract", placeholder="0x…")
            recipient = st.text_input(t("pl3.mint.recipient"), key="pl3_recipient_tw", placeholder="0x…")
        with t2:
            rpc_url = st.text_input(t("pl3.mint.rpc"), value=web3_service.BASE_RPC_DEFAULT, key="pl3_rpc")
            private_key = st.text_input(
                t("pl3.mint.private_key"), type="password", key="pl3_pk", help=t("pl3.mint.private_key_help"),
            )
        batch_mode = st.checkbox(
            t("pl3.mint.batch_mode"), value=len(assets) > 1,
            key="pl3_tw_batch", disabled=len(assets) < 2, help=t("pl3.mint.batch_mode_help"),
        )
        ready = all([contract, recipient, private_key]) and pinned == len(assets)
        if st.button(
            t("pl3.mint.btn_thirdweb", n=len(assets)), type="primary",
            width='stretch', key="pl3_mint_tw", disabled=not ready,
        ):
            if batch_mode and len(assets) > 1:
                _mint_batch_thirdweb(assets, private_key, contract, recipient, rpc_url)
            else:
                _mint_all_thirdweb(assets, private_key, contract, recipient, rpc_url)
    else:
        c1, c2 = st.columns(2)
        with c1:
            cm_key = st.text_input(t("pl3.mint.cm_key"), type="password", key="pl3_cm_key")
            cm_collection = st.text_input(t("pl3.mint.cm_coll"), key="pl3_cm_coll")
        with c2:
            recipient = st.text_input(
                t("pl3.mint.recipient"), key="pl3_recipient_cm", placeholder=t("pl3.mint.recipient_ph"),
            )
            staging = st.checkbox(t("pl3.mint.staging"), value=True, key="pl3_cm_staging")
        ready = all([cm_key, cm_collection, recipient]) and pinned == len(assets)
        if st.button(
            t("pl3.mint.btn_crossmint", n=len(assets)), type="primary",
            width='stretch', key="pl3_mint_cm", disabled=not ready,
        ):
            _mint_all_crossmint(assets, cm_key, cm_collection, recipient, chain, staging)

    if not pinned or pinned < len(assets):
        st.caption(t("pl3.mint.need_pin"))


def _cleanup_after_mint(assets: list[dict]) -> None:
    """Після успішного мінтингу прибирає тимчасові файли з temp_assets/.

    Зображення вже в IPFS (image_uri) — локальні копії більше не потрібні.
    Якщо хоч один токен упав, файли лишаються для повторної спроби.
    """
    if any((a.get("mint_result") or {}).get("status") == "error" for a in assets):
        return
    removed = network_config.cleanup_files([a["path"] for a in assets if a.get("path")])
    removed += network_config.cleanup_static_assets()
    if removed:
        st.info(t("pl3.mint.cleanup", n=removed))


def _mint_batch_thirdweb(assets, private_key, contract, recipient, rpc_url) -> None:
    """Одна multicall-транзакція на всю чергу: спільний tx hash для всіх токенів."""
    try:
        with st.spinner(t("pl3.mint.batch_spin", n=len(assets))):
            result = web3_service.mint_thirdweb_batch(
                private_key, contract, recipient, [a["token_uri"] for a in assets], rpc_url,
            )
        for item in assets:
            item["mint_result"] = result
    except Exception as e:
        for item in assets:
            item["mint_result"] = {"status": "error", "error": str(e)}
    st.session_state[MINT_ASSETS] = assets
    _cleanup_after_mint(assets)


def _mint_all_thirdweb(assets, private_key, contract, recipient, rpc_url) -> None:
    progress = st.progress(0, text=t("pl3.mint.progress"))
    for i, item in enumerate(assets):
        progress.progress(
            i / len(assets),
            text=t("pl3.mint.token_progress", i=i + 1, total=len(assets)),
        )
        try:
            item["mint_result"] = web3_service.mint_thirdweb(
                private_key, contract, recipient, item["token_uri"], rpc_url,
            )
        except Exception as e:
            item["mint_result"] = {"status": "error", "error": str(e)}
    progress.empty()
    st.session_state[MINT_ASSETS] = assets
    _cleanup_after_mint(assets)


def _mint_all_crossmint(assets, api_key, collection_id, recipient, chain, staging) -> None:
    progress = st.progress(0, text=t("pl3.mint.progress"))
    for i, item in enumerate(assets):
        progress.progress(
            i / len(assets),
            text=t("pl3.mint.token_progress", i=i + 1, total=len(assets)),
        )
        try:
            payload = web3_service.build_crossmint_payload(recipient, chain, item["metadata"])
            resp = web3_service.mint_crossmint(api_key, collection_id, payload, staging)
            item["mint_result"] = {"status": resp.get("onChain", {}).get("status", "pending"), "id": resp.get("id", "")}
        except Exception as e:
            item["mint_result"] = {"status": "error", "error": str(e)}
    progress.empty()
    st.session_state[MINT_ASSETS] = assets
    _cleanup_after_mint(assets)


def _render_results(assets: list[dict]) -> None:
    dash = t("pl3.results.dash")
    col_num = t("pl3.results.col_num")
    col_name = t("pl3.results.col_name")
    col_uri = t("pl3.results.col_uri")
    col_status = t("pl3.results.col_status")
    col_tx = t("pl3.results.col_tx")
    rows = [
        {
            col_num: i + 1,
            col_name: a.get("name", ""),
            col_uri: a.get("token_uri", dash),
            col_status: (a.get("mint_result") or {}).get("status", dash),
            col_tx: (a.get("mint_result") or {}).get("tx_hash", "")
            or (a.get("mint_result") or {}).get("id", "")
            or (a.get("mint_result") or {}).get("error", ""),
        }
        for i, a in enumerate(assets)
    ]
    if any(r[col_uri] != dash or r[col_status] != dash for r in rows):
        st.divider()
        st.markdown(t("pl3.results.title"))
        st.dataframe(rows, width='stretch', hide_index=True)
