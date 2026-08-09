"""Export Center v1 — картки платформ поверх export_bundle (W2.1)."""

from __future__ import annotations

import json

import streamlit as st

import ipfs
import network_config
from services import export_bundle, image_upscale, payment_service
from services import collection_naming, rarity_report, mint_path
from services import project_service
from services.ipfs_storage import PinataError, PinataService
from state.pipeline_state import APPROVED_CONTENT, MINT_ASSETS
from ui import billing_ui
from ui import quality_checklist
from ui.quality_checklist import PREFLIGHT_QC_FOCUS, QC_FORCE_EXPAND_KEY, QC_FOCUS_KEY
from ui_strings import t, ui_lang

EC_PLATFORM_KEY = "ec_platform"
EC_PATH_KEY = "ec_mint_path"
EC_PATH_RECORDED_KEY = "ec_mint_path_recorded"

# id → (label i18n key, recommended badge, w3ir special)
PLATFORM_CARDS: tuple[tuple[str, str, bool, bool], ...] = (
    ("thirdweb", "ec.card.thirdweb", True, False),
    ("opensea", "ec.card.opensea", False, False),
    ("metaplex", "ec.card.metaplex", False, False),
    ("generic", "ec.card.generic", False, False),
    ("w3ir", "ec.card.w3ir", False, True),
    ("sugar", "ec.card.sugar", False, True),
)

# Контейнерні профілі (поза PLATFORMS): власна гілка збірки, без ipfs_publish.
_CONTAINER_PLATFORMS = ("w3ir", "sugar")


def _assets_with_images(assets: list[dict], *, upscale: bool = False) -> list[dict]:
    out = []
    for a in assets:
        item = dict(a)
        path = a.get("path")
        if path and not item.get("image_bytes"):
            try:
                item["image_bytes"] = network_config.read_asset(path)
            except (OSError, ValueError):
                # недоступний/недозволений шлях → лишаємо без байтів; валідація
                # позначить «missing image» замість падіння всього Export Center
                pass
        out.append(item)
    return image_upscale.apply_to_assets(out, upscale=upscale)


def _issue_text(code: str, index: int | None) -> str:
    key = f"ec.issue.{code}"
    if index is not None:
        return t(key, n=index)
    return t(key)


def _render_issues(
    errors: list[tuple[str, int | None]],
    warnings: list[tuple[str, int | None]],
    *,
    qc_links: bool = False,
) -> bool:
    """Показує помилки/попередження. Повертає True якщо експорт дозволено."""
    for code, idx in errors:
        st.error(_issue_text(code, idx))
    for code, idx in warnings:
        focus = PREFLIGHT_QC_FOCUS.get(code) if qc_links else None
        if focus:
            col_w, col_b = st.columns([6, 1])
            with col_w:
                st.warning(_issue_text(code, idx))
            with col_b:
                if st.button(
                    t("ec.preflight_qc_btn"),
                    key=f"ec_qc_jump_{code}_{idx or 0}",
                    width='stretch',
                ):
                    st.session_state[QC_FOCUS_KEY] = focus
                    st.session_state[QC_FORCE_EXPAND_KEY] = True
                    st.rerun()
        else:
            st.warning(_issue_text(code, idx))
    return not errors


def _render_naming_wizard(assets: list[dict], collection_name: str) -> None:
    """CN-1: EN naming + description template."""
    with st.expander(t("ec.naming.title"), expanded=False):
        st.caption(t("ec.naming.caption"))
        brand_default = collection_name or st.session_state.get("pl3_coll_name", "")
        brand = st.text_input(
            t("ec.naming.brand"),
            value=brand_default,
            key="ec_naming_brand",
        )
        tagline = st.text_input(
            t("ec.naming.tagline"),
            placeholder=t("ec.naming.tagline_ph"),
            key="ec_naming_tagline",
        )
        col_h, col_fill = st.columns([4, 1])
        with col_h:
            hashtags = st.text_input(
                t("ec.naming.hashtags"),
                key="ec_naming_hashtags",
                help=t("ec.naming.hashtags_help"),
            )
        with col_fill:
            st.write("")
            if st.button(t("ec.naming.fill_tags"), key="ec_naming_fill_tags", width='stretch'):
                st.session_state["ec_naming_hashtags"] = collection_naming.default_hashtags(brand)
                st.rerun()
        example = collection_naming.token_name(brand, 1) if brand.strip() else "—"
        st.caption(t("ec.naming.preview", example=example))
        if st.button(
            t("ec.naming.apply", n=len(assets)),
            key="ec_naming_apply",
            width='stretch',
            disabled=not brand.strip(),
        ):
            if not brand.strip():
                st.warning(t("ec.naming.need_brand"))
            else:
                desc = collection_naming.build_description(
                    brand, len(assets), tagline=tagline, hashtags=hashtags,
                )
                updated = collection_naming.apply_naming(assets, brand, desc)
                st.session_state[MINT_ASSETS] = updated
                if len(st.session_state.get(APPROVED_CONTENT, [])) == len(updated):
                    st.session_state[APPROVED_CONTENT] = [dict(x) for x in updated]
                st.success(t("ec.naming.applied", n=len(updated)))
                st.rerun()


def _render_qc_soft_gate(score: int | None) -> None:
    """CN-2: advisory banner за score (не блокує export)."""
    if score is None:
        return
    if score < 60:
        st.warning(t("ec.qc_gate_low", score=score))
    elif score < 75:
        st.warning(t("ec.qc_gate_warn", score=score))


def _render_rarity_report(assets: list[dict]) -> None:
    summary = rarity_report.summarize_collection(assets)
    default_open = bool(summary and len(assets) > 1)
    with st.expander(t("ec.rarity.title"), expanded=default_open):
        if not summary:
            st.caption(t("ec.rarity.empty"))
            return
        skewed = rarity_report.skewed_traits(assets)
        for tr in skewed[:3]:
            st.warning(t(
                "ec.rarity.skew_warn",
                category=tr.get("category", ""),
                trait=tr.get("trait", ""),
                pct=tr.get("pct", 0),
            ))
        tiers = summary.get("tier_counts") or {}
        if tiers:
            cols = st.columns(min(len(tiers), 4))
            for col, (tier, count) in zip(cols, sorted(tiers.items(), key=lambda x: x[0])):
                col.metric(tier, count)
        st.caption(t("ec.rarity.rank_caption"))
        st.dataframe(summary["rank_rows"], width='stretch', hide_index=True)
        st.caption(t("ec.rarity.trait_caption"))
        st.dataframe(summary["trait_rows"], width='stretch', hide_index=True)
        md = rarity_report.format_markdown(summary, st.session_state.get("pl3_coll_name", ""))
        st.download_button(
            t("ec.rarity.download_md"),
            md,
            file_name="rarity-report.md",
            mime="text/markdown",
            width='stretch',
            key="ec_rarity_md",
        )


def _wallet_for_funnel() -> str:
    return (
        billing_ui.connected_wallet()
        or st.session_state.get("wallet_address", "")
        or ""
    )


def _record_platform_intent(platform: str, *, path_id: str | None = None, source: str) -> None:
    """Один intent на зміну платформи/шляху (анти-спам у session_state)."""
    kind = None
    if path_id:
        resolved = mint_path.resolve_path(path_id)
        if resolved:
            kind = resolved[1]
    sig = f"{source}:{path_id or ''}:{platform}"
    if st.session_state.get(EC_PATH_RECORDED_KEY) == sig:
        return
    mint_path.record_mint_path_intent(
        _wallet_for_funnel(),
        platform=platform,
        path_kind=kind,
        path_id=path_id,
        source=source,
    )
    st.session_state[EC_PATH_RECORDED_KEY] = sig


def _render_mint_path_chooser() -> None:
    """R2-A: «Який шлях обрати?» — не-дев → EVM visual; Solana → CLI; під ключ → concierge."""
    st.markdown(t("ec.path.title"))
    st.caption(t("ec.path.caption"))
    if EC_PATH_KEY not in st.session_state:
        st.session_state[EC_PATH_KEY] = "evm_easy"

    cols = st.columns(4)
    path_buttons = (
        ("evm_easy", "ec.path.evm_easy"),
        ("evm_opensea", "ec.path.evm_opensea"),
        ("solana_dev", "ec.path.solana_dev"),
        ("concierge", "ec.path.concierge"),
    )
    for col, (pid, label_key) in zip(cols, path_buttons):
        with col:
            selected = st.session_state[EC_PATH_KEY] == pid
            if st.button(
                t(label_key),
                key=f"ec_path_{pid}",
                width='stretch',
                type="primary" if selected else "secondary",
            ):
                st.session_state[EC_PATH_KEY] = pid
                resolved = mint_path.resolve_path(pid)
                if resolved and pid != "concierge":
                    platform, _kind = resolved
                    st.session_state[EC_PLATFORM_KEY] = platform
                    _record_platform_intent(platform, path_id=pid, source="path_chooser")
                elif pid == "concierge":
                    _record_platform_intent("concierge", path_id=pid, source="path_chooser")
                st.rerun()

    path_id = st.session_state[EC_PATH_KEY]
    hint_key = f"ec.path.hint.{path_id}"
    st.info(t(hint_key))
    if path_id == "solana_dev":
        st.caption(t("ec.path.solana_dev_note"))


def _render_concierge_form(collection_name: str) -> None:
    """R2-B: заявка «Launch it for you» — email + мережа; Telegram оператору."""
    expanded = st.session_state.get(EC_PATH_KEY) == "concierge"
    with st.expander(t("ec.concierge.title"), expanded=expanded):
        st.markdown(t("ec.concierge.body"))
        email = st.text_input(
            t("ec.concierge.email"),
            key="ec_concierge_email",
            placeholder="you@example.com",
        )
        chain = st.selectbox(
            t("ec.concierge.chain"),
            options=["solana", "base", "other"],
            format_func=lambda c: t(f"ec.concierge.chain.{c}"),
            key="ec_concierge_chain",
        )
        supply = int(st.number_input(
            t("ec.concierge.supply"),
            min_value=0,
            max_value=100_000,
            value=0,
            step=1,
            key="ec_concierge_supply",
            help=t("ec.concierge.supply_help"),
        ))
        notes = st.text_area(
            t("ec.concierge.notes"),
            key="ec_concierge_notes",
            placeholder=t("ec.concierge.notes_ph"),
            height=80,
        )
        if st.button(t("ec.concierge.submit"), key="ec_concierge_submit", type="primary"):
            ok, err = mint_path.submit_concierge_request(
                _wallet_for_funnel(),
                email=email,
                collection_name=collection_name or st.session_state.get("pl3_coll_name", ""),
                preferred_chain=str(chain),
                supply=supply or None,
                notes=notes,
            )
            if ok:
                st.success(t("ec.concierge.ok"))
            else:
                st.error(t(err or "ec.concierge.err_email"))


def _render_platform_cards() -> str:
    if EC_PLATFORM_KEY not in st.session_state:
        st.session_state[EC_PLATFORM_KEY] = "thirdweb"

    st.markdown(t("ec.pick_platform"))
    # 2 ряди по 3 картки — читабельніше на вузькому екрані, ніж 6 колонок в ряд.
    for row in (PLATFORM_CARDS[:3], PLATFORM_CARDS[3:]):
        cols = st.columns(len(row))
        for col, (pid, label_key, recommended, _w3ir) in zip(cols, row):
            with col:
                label = t(label_key)
                if recommended:
                    label = f"🟢 {label}"
                if pid in ("metaplex", "sugar"):
                    label = f"🛠 {label}"
                selected = st.session_state[EC_PLATFORM_KEY] == pid
                btn_type = "primary" if selected else "secondary"
                if st.button(label, key=f"ec_pick_{pid}", width='stretch', type=btn_type):
                    st.session_state[EC_PLATFORM_KEY] = pid
                    _record_platform_intent(pid, source="platform_card")
                    st.rerun()
    platform = st.session_state[EC_PLATFORM_KEY]
    if platform in ("metaplex", "sugar"):
        st.caption(t("ec.card.solana_me_hint"))
        st.caption(t("ec.card.solana_dev_only"))
    return platform


def _render_structure_preview(platform: str, n_assets: int, collection_name: str) -> None:
    """#8: показує, що саме потрапить у ZIP, ДО збірки (без генерації архіву)."""
    lines = export_bundle.describe_bundle_structure(platform, n_assets, collection_name)
    if not lines:
        return
    with st.expander(t("ec.structure.title"), expanded=False):
        st.caption(t("ec.structure.caption"))
        st.code("\n".join(lines), language="text")


def _render_guide(platform: str) -> None:
    guide_key = f"ec.guide.{platform}"
    with st.expander(t("ec.guide_title"), expanded=False):
        st.markdown(t("ec.guide_intro"))
        st.divider()
        st.markdown(t(guide_key))
        if platform == "sugar":
            st.divider()
            st.markdown(t("ec.sugar_runbook"))


def _metaplex_fields() -> tuple[str, int, str]:
    m1, m2, m3 = st.columns(3)
    with m1:
        symbol = st.text_input(t("pl3.export.symbol"), max_chars=10, key="ec_exp_symbol", placeholder="APES")
    with m2:
        royalty_bps = int(
            st.number_input(t("pl3.export.royalty"), 0.0, 50.0, 5.0, 0.5, key="ec_exp_royalty") * 100
        )
    with m3:
        creator = st.text_input(t("pl3.export.creator"), key="ec_exp_creator", placeholder="—")
    return symbol, royalty_bps, creator


def _candy_guard_fields(creator: str) -> "export_bundle.CandyGuards":
    """Форма guards Candy Machine → CandyGuards. treasury за замовч. = creator."""
    with st.expander(t("ec.candy.guards_title"), expanded=False):
        g1, g2 = st.columns(2)
        with g1:
            price = float(st.number_input(t("ec.candy.price"), 0.0, 1000.0, 0.0, 0.1, key="ec_candy_price"))
            treasury = st.text_input(
                t("ec.candy.treasury"), key="ec_candy_treasury", help=t("ec.candy.treasury_help"),
            ).strip()
        with g2:
            start = st.text_input(
                t("ec.candy.start"), key="ec_candy_start", placeholder="2026-07-01T16:00:00Z",
            ).strip()
            end = st.text_input(
                t("ec.candy.end"), key="ec_candy_end", placeholder="2026-07-08T16:00:00Z",
            ).strip()
            limit = int(st.number_input(t("ec.candy.limit"), 0, 100000, 0, 1, key="ec_candy_limit"))
        allowlist_raw = st.text_area(
            t("ec.candy.allowlist"), key="ec_candy_allowlist", help=t("ec.candy.allowlist_help"),
        ).strip()
    allowlist = [ln.strip() for ln in allowlist_raw.splitlines() if ln.strip()] or None
    return export_bundle.CandyGuards(
        price_sol=price or None,
        treasury=(treasury or creator).strip(),
        start_date=start or None,
        end_date=end or None,
        mint_limit=limit or None,
        allowlist=allowlist,
    )


def _record_export_funnel() -> None:
    payment_service.record_funnel_event(_wallet_for_funnel(), "export")


def _pinata_jwt_for_upload(wallet: str) -> str | None:
    """Режим IPFS: W3IR (бонус для поповнених) або власний Pinata JWT."""
    platform_jwt = ipfs.get_pinata_jwt()
    eligible = ipfs.platform_pinata_eligible(wallet)

    if platform_jwt and eligible:
        mode = st.radio(
            t("ec.ipfs.mode.label"),
            options=["platform", "own"],
            format_func=lambda m: t(f"ec.ipfs.mode.{m}"),
            horizontal=True,
            key="ec_ipfs_mode",
        )
        st.caption(t("ec.ipfs.mode.platform_help" if mode == "platform" else "ec.ipfs.mode.own_help"))
    elif platform_jwt:
        st.caption(t("ec.ipfs.platform_paid_only"))
        mode = "own"
        st.caption(t("ec.ipfs.mode.own_help"))
    else:
        st.caption(t("ec.ipfs.no_platform_key"))
        mode = "own"
        st.caption(t("ec.ipfs.mode.own_help"))

    user_jwt = ""
    if mode == "own":
        user_jwt = st.text_input(
            t("pl3.mint.pinata_jwt"),
            type="password",
            key="ec_export_jwt",
            placeholder="eyJ…",
        ).strip()
    return ipfs.resolve_upload_jwt(wallet, mode, user_jwt)


def _store_mint_zip(
    platform: str,
    items: list[dict],
    collection_name: str,
    dl_name: str,
    *,
    ipfs_result: dict | None = None,
    lang: str | None = None,
    **kw,
) -> None:
    """ZIP для мінту: з ipfs-manifest.json, якщо вже є Pinata-результат."""
    st.session_state["ec_zip_bytes"] = export_bundle.build_zip(
        platform, items, collection_name, ipfs_result=ipfs_result, lang=lang or ui_lang(), **kw,
    )
    st.session_state["ec_zip_name"] = dl_name
    _record_export_funnel()


def render(assets: list[dict], collection_name: str) -> None:
    """Export Center: header, валідація, картки платформ, ZIP / W3IR / IPFS."""
    ready_images = sum(1 for a in assets if a.get("path") or a.get("image_bytes"))
    st.markdown(t("ec.header.title"))
    st.caption(t("ec.header.subtitle"))
    
    # Етап 1.5: CTA-банер живого кейсу
    if ui_lang() == "uk":
        st.info(
            "💡 **Бажаєте побачити результат мінту наживо?** "
            "Перегляньте нашу діючу Genesis-колекцію на сторінці продажу: [mint.w3ir.io](https://mint.w3ir.io), "
            "де також можна протестувати оплату звичайною банківською карткою."
        )
    else:
        st.info(
            "💡 **Want to see the minting result live?** "
            "Check out our live Genesis collection on the minting page: [mint.w3ir.io](https://mint.w3ir.io), "
            "where you can also test paying with a credit card."
        )

    c1, c2, c3 = st.columns(3)
    c1.metric(t("ec.stat.total"), len(assets))
    c2.metric(t("ec.stat.ready"), ready_images)
    c3.metric(t("ec.stat.export"), ready_images)

    # UX-5: застереження про неповний дроп — у черзі менше активів, ніж було
    # згенеровано промптів (планований supply). Не блокує експорт, лише попереджає,
    # щоб користувач не зібрав випадково 10 із 50 запланованих.
    planned = len(st.session_state.get("generated_prompts", []))
    if planned and len(assets) < planned:
        st.warning(t("ec.incomplete_warn", approved=len(assets), planned=planned))

    min_rating = int(st.slider(
        t("ec.min_rating"), 0, 5, 0, key="ec_min_rating", help=t("ec.min_rating_help"),
    ))
    items_for_check = _assets_with_images(assets)
    errors, warnings = export_bundle.validate_export_assets(
        items_for_check, min_curator_rating=min_rating,
    )
    can_export = _render_issues(errors, warnings, qc_links=True)

    if items_for_check:
        st.info(t("ec.qc_banner"))
        _render_naming_wizard(items_for_check, collection_name)

    platform = st.session_state.get(EC_PLATFORM_KEY, "thirdweb")
    royalty_bps = int(st.session_state.get("ec_exp_royalty", 5.0) * 100) if platform in ("metaplex", "sugar") else 500
    symbol = str(st.session_state.get("ec_exp_symbol", "") or "")
    mint_price_sol = None
    if platform == "sugar":
        mint_price_sol = float(st.session_state.get("ec_candy_price", 0.0))
    qc_score = quality_checklist.render_quality_checklist(
        items_for_check,
        collection_name,
        platform=platform,
        royalty_bps=royalty_bps,
        symbol=symbol,
        mint_price_sol=mint_price_sol,
        ipfs_pinned=bool(st.session_state.get("ec_ipfs_result")),
        ipfs_result=st.session_state.get("ec_ipfs_result"),
        planned_count=planned,
        upscale_enabled=bool(st.session_state.get("ec_upscale", False)),
        upscale_available=image_upscale.upscale_available(),
        preflight_errors=errors,
        preflight_warnings=warnings,
    )
    _render_qc_soft_gate(qc_score)

    _render_rarity_report(assets)

    upscale_on = False
    if image_upscale.upscale_available():
        needs_upscale = image_upscale.collection_needs_upscale(items_for_check)
        if needs_upscale and not st.session_state.get("ec_upscale"):
            st.info(t("ec.upscale_nudge", target=image_upscale.TARGET_MAX_DEFAULT))
        default_upscale = bool(st.session_state.get("ec_upscale", needs_upscale))
        upscale_on = st.checkbox(
            t("ec.export.upscale"),
            value=default_upscale,
            key="ec_upscale",
            help=t("ec.export.upscale_help"),
        )

    _render_mint_path_chooser()
    _render_concierge_form(collection_name)
    platform = _render_platform_cards()
    _render_structure_preview(platform, len(assets), collection_name)
    _render_guide(platform)

    is_w3ir = platform == "w3ir"
    is_sugar = platform == "sugar"
    is_container = platform in _CONTAINER_PLATFORMS

    symbol, royalty_bps, creator = "", 500, ""
    guards = None
    if platform in ("metaplex", "sugar"):
        symbol, royalty_bps, creator = _metaplex_fields()
    if is_sugar:
        guards = _candy_guard_fields(creator)
    kw = dict(symbol=symbol, royalty_bps=royalty_bps, creator=creator)
    ipfs_res = st.session_state.get("ec_ipfs_result")

    if is_w3ir:
        zip_label = t("ec.build.w3ir")
    elif is_sugar:
        zip_label = t("ec.build.sugar")
    else:
        zip_label = t("pl3.export.build_zip")
    if is_w3ir:
        dl_name = f"{collection_name or 'collection'}{export_bundle.W3IR_PACKAGE_EXT}"
    elif is_sugar:
        dl_name = f"{collection_name or 'collection'}{export_bundle.CANDY_MACHINE_EXT}"
    else:
        dl_name = f"{collection_name or 'bundle'}-{platform}.zip"

    col1, col2 = st.columns(2)
    with col1:
        if not is_container:
            st.caption(t("ec.zip.hint_ipfs" if ipfs_res else "ec.zip.hint_local"))
        if st.button(
            zip_label,
            width='stretch',
            key="ec_build_zip",
            disabled=not can_export,
        ):
            items = _assets_with_images(assets, upscale=upscale_on)
            errors, warnings = export_bundle.validate_export_assets(
                items, min_curator_rating=int(st.session_state.get("ec_min_rating", 0)),
            )
            if not _render_issues(errors, warnings):
                st.stop()
            if is_w3ir:
                st.session_state["ec_zip_bytes"] = export_bundle.build_w3ir_package_zip(
                    items, collection_name, lang=ui_lang(),
                )
            elif is_sugar:
                if not creator.strip():
                    st.error(t("ec.candy.creator_required"))
                    st.stop()
                st.session_state["ec_zip_bytes"] = export_bundle.build_candy_machine_package_zip(
                    items, collection_name, guards=guards, lang=ui_lang(), **kw,
                )
            else:
                _store_mint_zip(
                    platform, items, collection_name, dl_name,
                    ipfs_result=ipfs_res, **kw,
                )
            st.rerun()
        if st.session_state.get("ec_zip_bytes"):
            st.download_button(
                t("pl3.export.download_zip"),
                st.session_state["ec_zip_bytes"],
                file_name=st.session_state.get("ec_zip_name", "bundle.zip"),
                mime="application/zip",
                width='stretch',
                key="ec_dl_zip",
            )
    with col2:
        st.markdown(f"**{t('ec.ipfs.title')}**")
        if not is_container:
            st.caption(t("ec.ipfs.flow"))
        if is_container:
            # disabled-кнопка не показує help-tooltip при hover (браузер глушить
            # події) → виводимо причину видимою підказкою (BUG #2 з UI-огляду)
            st.caption(t("ec.ipfs.sugar_hint") if is_sugar else t("ec.ipfs.w3ir_hint"))
        wallet = billing_ui.connected_wallet()
        jwt = _pinata_jwt_for_upload(wallet) if not is_container else None
        if st.button(
            t("pl3.export.ipfs_folder"),
            width='stretch',
            key="ec_ipfs_folder",
            disabled=not jwt or not can_export or is_container,
            help=(
                t("ec.ipfs.sugar_hint") if is_sugar
                else t("ec.ipfs.w3ir_hint") if is_w3ir
                else None
            ),
        ):
            try:
                svc = PinataService(jwt)

                def _step_upload(files, name):
                    if name.endswith("-images"):
                        st.write("📤 …")
                    else:
                        st.write("📌 …")
                    return svc.pin_directory(files, name)

                with st.status(t("pl3.export.ipfs_spinner"), expanded=True) as status:
                    items = _assets_with_images(assets, upscale=upscale_on)
                    errors, warnings = export_bundle.validate_export_assets(
                        items, min_curator_rating=int(st.session_state.get("ec_min_rating", 0)),
                    )
                    if not _render_issues(errors, warnings):
                        st.stop()
                    pub_platform = platform if not is_container else "opensea"
                    ipfs_res = export_bundle.ipfs_publish(
                        pub_platform,
                        items,
                        jwt,
                        collection_name,
                        uploader=_step_upload,
                        **kw,
                    )
                    st.session_state["ec_ipfs_result"] = ipfs_res
                    _store_mint_zip(
                        pub_platform, items, collection_name,
                        f"{collection_name or 'bundle'}-{pub_platform}-mint.zip",
                        ipfs_result=ipfs_res, **kw,
                    )
                    project_service.autosave(billing_ui.connected_wallet())
                    status.update(label="✓", state="complete", expanded=False)
                st.rerun()
            except PinataError as e:
                st.error(f"IPFS: {e}")
            except Exception as e:
                st.error(str(e))
        res = st.session_state.get("ec_ipfs_result")
        if res:
            st.success(t("pl3.export.ipfs_done", n=res["count"]))
            if st.session_state.get("ec_zip_bytes") and not is_container:
                st.info(t("ec.ipfs.zip_ready"))
            st.caption(t("ec.ipfs.base_uri"))
            st.code(res["base_uri"], language="text")
            st.caption(t("ec.ipfs.images_uri"))
            st.code(res["image_base_uri"], language="text")
            manifest = export_bundle.ipfs_manifest_document(
                res, collection_name=collection_name, platform=platform,
            )
            st.download_button(
                t("ec.ipfs.download_manifest"),
                json.dumps(manifest, ensure_ascii=False, indent=2),
                file_name="ipfs-manifest.json",
                mime="application/json",
                width='stretch',
                key="ec_dl_ipfs_manifest",
            )
