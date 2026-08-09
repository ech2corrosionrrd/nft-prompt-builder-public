"""i18n: NFT Quality Checklist (Export Center AI assistant)."""

STRINGS: dict[str, dict[str, str]] = {
    # ── UI shell ──
    'qc.title': {
        'uk': '### 🤖 NFT Quality Checklist',
        'en': '### 🤖 NFT Quality Checklist',
    },
    'qc.subtitle': {
        'uk': 'SEO + Technical + Market Fit перед мінтом. **Лише рекомендації** — не блокує експорт.',
        'en': 'SEO + Technical + Market Fit before mint. **Recommendations only** — does not block export.',
    },
    'qc.workflow_guide': {
        'uk': '**Як користуватися:** 1) відмітьте self-check нижче · 2) **Запустити перевірку** (безкоштовно) · 3) за потреби **AI deep dive** · 4) виправте warn → зберіть ZIP/IPFS.',
        'en': '**How to use:** 1) tick self-check below · 2) **Run checklist** (free) · 3) optional **AI deep dive** · 4) fix warnings → build ZIP/IPFS.',
    },
    'qc.disclaimer': {
        'uk': 'ℹ️ Це advisory-чекліст, не юридична чи фінансова порада. Рішення про публікацію — за вами.',
        'en': 'ℹ️ This is an advisory checklist, not legal or financial advice. You decide whether to publish.',
    },
    'qc.focus_hint': {
        'uk': '👈 Повʼязано з попередженням preflight вище',
        'en': '👈 Linked to the preflight warning above',
    },
    'qc.run': {
        'uk': '▶️ Запустити перевірку (безкоштовно)',
        'en': '▶️ Run checklist (free)',
    },
    'qc.ai_section_title': {
        'uk': '**AI (опційно)**',
        'en': '**AI (optional)**',
    },
    'qc.ai_run': {
        'uk': '✨ AI-поради ({credits} кред.)',
        'en': '✨ AI tips ({credits} cr)',
    },
    'qc.deep_dive_run': {
        'uk': '🔬 AI deep dive ({credits} кред.)',
        'en': '🔬 AI deep dive ({credits} cr)',
    },
    'qc.deep_dive_hint': {
        'uk': 'Deep dive: thumbnail readability + style consistency + персональні поради.',
        'en': 'Deep dive: thumbnail readability + style consistency + personalized tips.',
    },
    'qc.ai_need_key': {
        'uk': 'Для AI-порад потрібен OpenAI API key (sidebar або .env).',
        'en': 'AI tips require an OpenAI API key (sidebar or .env).',
    },
    'qc.ai_no_credits': {
        'uk': 'Недостатньо кредитів для AI-порад.',
        'en': 'Not enough credits for AI tips.',
    },
    'qc.score': {
        'uk': 'Оцінка якості',
        'en': 'Quality score',
    },
    'qc.band.ready': {
        'uk': '**90–100** — готові до публікації',
        'en': '**90–100** — ready to publish',
    },
    'qc.band.minor': {
        'uk': '**75–89** — потрібні невеликі правки',
        'en': '**75–89** — minor fixes recommended',
    },
    'qc.band.major': {
        'uk': '**60–74** — багато доопрацювань',
        'en': '**60–74** — significant work needed',
    },
    'qc.band.risk': {
        'uk': '**< 60** — високий ризик слабкого дропу',
        'en': '**< 60** — high risk of a weak drop',
    },
    'qc.cat.visual': {'uk': '1. Візуальна якість', 'en': '1. Visual quality'},
    'qc.cat.metadata': {'uk': '2. Metadata', 'en': '2. Metadata'},
    'qc.cat.technical': {'uk': '3. Технічні аспекти', 'en': '3. Technical'},
    'qc.cat.economics': {'uk': '4. Економіка та royalties', 'en': '4. Economics & royalties'},
    'qc.cat.marketing': {'uk': '5. Маркетинг та NFT SEO', 'en': '5. Marketing & NFT SEO'},
    'qc.cat.legal': {'uk': '6. Юридичне та безпека', 'en': '6. Legal & safety'},
    'qc.ai_section': {'uk': '**AI-поради**', 'en': '**AI recommendations**'},
    'qc.ai.thumbnail_title': {
        'uk': '**Thumbnail readability (vision)**',
        'en': '**Thumbnail readability (vision)**',
    },
    'qc.ai.thumbnail_score': {
        'uk': 'Оцінка thumbnail: {score}/10',
        'en': 'Thumbnail score: {score}/10',
    },
    'qc.ai.thumbnail_ok': {
        'uk': 'Читабельні в малому розмірі.',
        'en': 'Readable at small size.',
    },
    'qc.ai.thumbnail_warn': {
        'uk': 'Можуть губитись деталі в thumbnail.',
        'en': 'May lose detail at thumbnail size.',
    },
    'qc.ai.style_title': {
        'uk': '**Style consistency (vision)**',
        'en': '**Style consistency (vision)**',
    },
    'qc.ai.style_score': {
        'uk': 'Оцінка стилю: {score}/10',
        'en': 'Style score: {score}/10',
    },
    'qc.ai.style_ok': {
        'uk': 'Стиль узгоджений між зразками.',
        'en': 'Style looks consistent across samples.',
    },
    'qc.ai.style_warn': {
        'uk': 'Є розбіжності стилю між NFT.',
        'en': 'Style varies between NFTs.',
    },
    'qc.ai.skipped': {
        'uk': 'Vision-перевірку пропущено: {reason}',
        'en': 'Vision check skipped: {reason}',
    },
    # ── Check items ──
    'qc.item.no_assets': {
        'uk': 'Немає активів для оцінки.',
        'en': 'No assets to evaluate.',
    },
    'qc.item.resolution_good': {
        'uk': 'Роздільність ~{px}px — відмінно (ціль 2000–3000px).',
        'en': 'Resolution ~{px}px — excellent (target 2000–3000px).',
    },
    'qc.item.resolution_ok': {
        'uk': 'Середня роздільність {px}px — прийнятно; для маркетплейсу краще ≥{target}px.',
        'en': 'Average resolution {px}px — acceptable; marketplaces prefer ≥{target}px.',
    },
    'qc.item.resolution_low': {
        'uk': 'Низька роздільність ({px}px). Upscale або регенеруйте ≥{target}px.',
        'en': 'Low resolution ({px}px). Upscale or regenerate at ≥{target}px.',
    },
    'qc.item.resolution_unknown': {
        'uk': 'Не вдалося визначити роздільність зображень.',
        'en': 'Could not determine image resolution.',
    },
    'qc.item.resolution_min_low': {
        'uk': 'Мінімальна сторона {px}px — замало для чіткого превʼю на ME/OpenSea.',
        'en': 'Minimum side {px}px — too small for sharp marketplace thumbnails.',
    },
    'qc.item.filesize_good': {
        'uk': 'Розмір файлів у нормі (< 15 MB).',
        'en': 'File sizes look good (< 15 MB).',
    },
    'qc.item.filesize_high': {
        'uk': 'Деякі файли важкі ({mb} MB) — стисніть до < 15 MB, якщо можливо.',
        'en': 'Some files are heavy ({mb} MB) — compress toward < 15 MB if possible.',
    },
    'qc.item.filesize_too_large': {
        'uk': 'Файл > {mb} MB — ризик лімітів платформи (макс. ~30 MB).',
        'en': 'File > {mb} MB — platform limits risk (max ~30 MB).',
    },
    'qc.item.qa_clean': {
        'uk': 'Auto-QA: без blank/blur/corrupt на вибірці.',
        'en': 'Auto-QA: no blank/blur/corrupt issues in sample.',
    },
    'qc.item.qa_issues': {
        'uk': 'Auto-QA: {count} проблем із {checked} перевірених — перегляньте на Етапі 2.',
        'en': 'Auto-QA: {count} issues in {checked} checked — review on Stage 2.',
    },
    'qc.item.format_png': {
        'uk': 'Формат PNG — оптимально для NFT.',
        'en': 'PNG format — ideal for NFTs.',
    },
    'qc.item.format_jpeg': {
        'uk': '{count} JPEG — PNG/WebP краще для якості.',
        'en': '{count} JPEG — PNG/WebP preferred for quality.',
    },
    'qc.item.upscale_hint': {
        'uk': 'Середня роздільність {px}px < {target}px — увімкніть Upscale перед ZIP/IPFS.',
        'en': 'Average resolution {px}px < {target}px — enable Upscale before ZIP/IPFS.',
    },
    'qc.item.upscale_on': {
        'uk': 'Upscale увімкнено — зображення будуть збільшені перед експортом.',
        'en': 'Upscale enabled — images will be enlarged before export.',
    },
    'qc.item.hashtags_good': {
        'uk': 'Хештеги в описах (~{count}) — добре для discoverability.',
        'en': 'Hashtags in descriptions (~{count}) — good for discoverability.',
    },
    'qc.item.hashtags_ok': {
        'uk': 'Мало хештегів (~{count}) — додайте {target}–5 релевантних у кінці опису.',
        'en': 'Few hashtags (~{count}) — add {target}–5 relevant tags at the end of descriptions.',
    },
    'qc.item.hashtags_missing': {
        'uk': 'Немає хештегів — додайте {target}–5 (#PFP, #generative тощо) без спаму.',
        'en': 'No hashtags — add {target}–5 (#PFP, #generative, etc.) without spam.',
    },
    'qc.item.external_url_ok': {
        'uk': 'Знайдено зовнішні URL у metadata ({count}) — сайт/Discord/roadmap.',
        'en': 'External URLs found in metadata ({count}) — site/Discord/roadmap.',
    },
    'qc.item.external_url_missing': {
        'uk': 'Немає URL у описах — додайте w3ir.io, Discord або roadmap.',
        'en': 'No URLs in descriptions — add w3ir.io, Discord, or your roadmap link.',
    },
    'qc.item.name_too_short': {
        'uk': '{count} назв коротші за {min} символи.',
        'en': '{count} names shorter than {min} characters.',
    },
    'qc.item.description_good': {
        'uk': 'Описи ~{chars} символів у середньому — добре для SEO.',
        'en': 'Descriptions ~{chars} chars on average — good for SEO.',
    },
    'qc.item.description_ok': {
        'uk': 'Описи ~{chars} символів — додайте історію/utility до ~{target}.',
        'en': 'Descriptions ~{chars} chars — add story/utility toward ~{target}.',
    },
    'qc.item.description_short': {
        'uk': 'Короткі описи (~{chars} симв.) — ціль ≥{target} для маркетплейсів.',
        'en': 'Short descriptions (~{chars} chars) — aim for ≥{target} on marketplaces.',
    },
    'qc.item.description_filled': {
        'uk': 'Усі токени мають опис.',
        'en': 'All tokens have descriptions.',
    },
    'qc.item.description_empty': {
        'uk': '{count} токенів з порожнім/коротким описом.',
        'en': '{count} tokens with empty/short descriptions.',
    },
    'qc.item.description_length_ok': {
        'uk': 'Довжина описів у межах (≤{max} символів) — без SEO-spam.',
        'en': 'Description lengths within limit (≤{max} chars) — no SEO spam.',
    },
    'qc.item.description_long': {
        'uk': '{count} описів занадто довгі (макс. {chars} симв., ціль ≤{max}) — скоротіть keyword stuffing.',
        'en': '{count} descriptions too long (max {chars} chars, aim ≤{max}) — trim keyword stuffing.',
    },
    'qc.item.name_length_ok': {
        'uk': 'Довжина назв у межах 3–60 символів.',
        'en': 'Name lengths within 3–60 characters.',
    },
    'qc.item.name_too_long': {
        'uk': '{count} назв > {max} символів — скоротіть для читабельності.',
        'en': '{count} names > {max} chars — shorten for readability.',
    },
    'qc.item.name_generic_template': {
        'uk': 'Усі назви «Token #N» — замініть на брендовий шаблон (Collection #42).',
        'en': 'All names are «Token #N» — use a branded pattern (Collection #42).',
    },
    'qc.item.name_branded': {
        'uk': 'Назви токенів не лише шаблонні Token #N.',
        'en': 'Token names are not only generic Token #N.',
    },
    'qc.item.name_mixed_template': {
        'uk': '{count} токенів із шаблоном Token #N — узгодьте naming.',
        'en': '{count} tokens use Token #N template — align naming.',
    },
    'qc.item.traits_present': {
        'uk': 'Атрибути (traits) присутні.',
        'en': 'Traits/attributes are present.',
    },
    'qc.item.traits_specific': {
        'uk': 'Traits виглядають специфічними (не лише «Blue»).',
        'en': 'Traits look specific (not just generic colors).',
    },
    'qc.item.traits_generic': {
        'uk': '{count} загальних trait-значень — уточніть («Deep Nebula» замість «Blue»).',
        'en': '{count} generic trait values — refine (e.g. «Deep Nebula» vs «Blue»).',
    },
    'qc.item.traits_missing': {
        'uk': 'Немає traits — додайте для rarity та фільтрів на ME.',
        'en': 'No traits — add them for rarity and marketplace filters.',
    },
    'qc.item.collection_named': {
        'uk': 'Назва колекції: «{name}».',
        'en': 'Collection name: «{name}».',
    },
    'qc.item.collection_unnamed': {
        'uk': 'Назва колекції порожня — задайте брендову назву.',
        'en': 'Collection name is empty — set a branded name.',
    },
    'qc.item.prompts_unique': {
        'uk': 'Промпти унікальні (немає дублікатів metadata).',
        'en': 'Prompts are unique (no metadata collisions).',
    },
    'qc.item.prompts_duplicate': {
        'uk': '{count} дублікатів промпту — ризик однакових NFT.',
        'en': '{count} duplicate prompts — risk of identical NFTs.',
    },
    'qc.item.rarity_balanced': {
        'uk': 'Рідкісність traits збалансована (жоден trait > 50% supply).',
        'en': 'Trait rarity is balanced (no trait > 50% of supply).',
    },
    'qc.item.rarity_skewed': {
        'uk': 'Trait «{trait_cat}: {trait}» у {pct}% колекції (+{extra} інших >50%).',
        'en': 'Trait «{trait_cat}: {trait}» appears in {pct}% of supply (+{extra} more >50%).',
    },
    'qc.item.json_all_valid': {
        'uk': 'Metadata JSON валідний для всіх {count} токенів.',
        'en': 'Metadata JSON valid for all {count} tokens.',
    },
    'qc.item.json_errors': {
        'uk': '{count}/{total} токенів з помилками JSON (напр. #{token}: {error}).',
        'en': '{count}/{total} tokens with JSON errors (e.g. #{token}: {error}).',
    },
    'qc.item.image_field_ok': {
        'uk': 'Поле image у JSON збігається з файлами бандлу ({count} токенів).',
        'en': 'JSON image field matches bundle files ({count} tokens).',
    },
    'qc.item.image_field_mismatch': {
        'uk': '{count} токенів: image у JSON ≠ файл (напр. #{token}: очікувалось «{expected}», є «{got}»).',
        'en': '{count} tokens: JSON image ≠ file (e.g. #{token}: expected «{expected}», got «{got}»).',
    },
    'qc.item.format_webp': {
        'uk': 'Усі зображення WebP ({count}) — перевірте підтримку на цільовому маркетплейсі.',
        'en': 'All images are WebP ({count}) — verify target marketplace support.',
    },
    'qc.item.format_webp_mixed': {
        'uk': 'Змішані формати: WebP {webp}, інші {other}.',
        'en': 'Mixed formats: WebP {webp}, other {other}.',
    },
    'qc.item.ipfs_pinned': {
        'uk': 'Pinata IPFS pin виконано (metadata CID {cid}…) — посилання готові для контракту.',
        'en': 'Pinata IPFS pinned (metadata CID {cid}…) — links ready for contract/drop.',
    },
    'qc.item.ipfs_reachable': {
        'uk': 'IPFS gateway відповідає (перевірено metadata + image URI).',
        'en': 'IPFS gateway reachable (metadata + image URI probed).',
    },
    'qc.item.ipfs_probe_failed': {
        'uk': 'IPFS pin є, але gateway не відповів: {detail}',
        'en': 'IPFS pinned but gateway probe failed: {detail}',
    },
    'qc.item.ipfs_probe_skipped': {
        'uk': 'IPFS probe пропущено (немає CID/URI для перевірки).',
        'en': 'IPFS probe skipped (no CID/URI to check).',
    },
    'qc.item.ipfs_sugar_ok': {
        'uk': 'Solana/Sugar завантажить assets при deploy — окремий IPFS опційний.',
        'en': 'Solana/Sugar uploads on deploy — separate IPFS optional.',
    },
    'qc.item.ipfs_local_zip': {
        'uk': 'Лише локальний ZIP — для OpenSea/EVM спочатку Pinata IPFS (кнопка IPFS).',
        'en': 'Local ZIP only — for OpenSea/EVM, Pinata IPFS first (IPFS button).',
    },
    'qc.download_json': {
        'uk': '⬇️ quality-report.json',
        'en': '⬇️ quality-report.json',
    },
    'qc.download_md': {
        'uk': '⬇️ quality-report.md',
        'en': '⬇️ quality-report.md',
    },
    'qc.checklist.section': {
        'uk': '**Self-check перед мінтом**',
        'en': '**Self-check before mint**',
    },
    'qc.checklist.hint': {
        'uk': 'Відмітьте, що вже зроблено — це змінює score marketing/legal (не блокує експорт). Зберігається в проєкті.',
        'en': 'Tick what you already have — updates marketing/legal score (does not block export). Saved with your project.',
    },
    'qc.checklist.marketing': {
        'uk': 'Маркетинг',
        'en': 'Marketing',
    },
    'qc.checklist.legal': {
        'uk': 'Legal',
        'en': 'Legal',
    },
    'qc.cb.discord': {
        'uk': 'Discord-сервер / спільнота',
        'en': 'Discord server / community',
    },
    'qc.cb.telegram': {
        'uk': 'Telegram-канал / чат',
        'en': 'Telegram channel / chat',
    },
    'qc.cb.twitter': {
        'uk': 'X (Twitter) акаунт / тред',
        'en': 'X (Twitter) account / thread',
    },
    'qc.cb.waitlist': {
        'uk': 'Waitlist / OG / allowlist',
        'en': 'Waitlist / OG / allowlist',
    },
    'qc.cb.utility': {
        'uk': 'Utility / roadmap для холдерів',
        'en': 'Utility / roadmap for holders',
    },
    'qc.cb.reveal_plan': {
        'uk': 'Reveal plan (blind / staged / instant)',
        'en': 'Reveal plan (blind / staged / instant)',
    },
    'qc.cb.rights_attestation': {
        'uk': 'Я автор; немає чужих брендів/персонажів без ліцензії',
        'en': 'I own the work; no third-party brands/characters without license',
    },
    'qc.cb.policy_review': {
        'uk': 'Переглянув політику платформи (NSFW/hate, audit для великих дропів)',
        'en': 'Reviewed platform policy (NSFW/hate, audit for large drops)',
    },
    'qc.item.platform_selected': {
        'uk': 'Платформа {platform} обрана — структура бандлу відповідає.',
        'en': 'Platform {platform} selected — bundle layout matches.',
    },
    'qc.item.platform_generic': {
        'uk': 'Generic ZIP — переконайтесь, що отримувач знає формат.',
        'en': 'Generic ZIP — ensure the recipient knows the format.',
    },
    'qc.item.platform_hint_opensea': {
        'uk': 'OpenSea Studio: Drop + baseURI з IPFS; banner/collection page; royalty у контракті.',
        'en': 'OpenSea Studio: Drop + IPFS baseURI; collection banner; royalties in contract.',
    },
    'qc.item.platform_hint_opensea_ipfs': {
        'uk': 'OpenSea вимагає IPFS baseURI — спочатку Pinata (кнопка IPFS тут).',
        'en': 'OpenSea needs an IPFS baseURI — Pinata first (IPFS button here).',
    },
    'qc.item.platform_hint_blur': {
        'uk': 'Blur (EVM): після мінту — verify контракт на explorer; лістинг часто через OpenSea/Blur агрегатор.',
        'en': 'Blur (EVM): after mint — verify contract on explorer; listings often via OpenSea/Blur aggregator.',
    },
    'qc.item.platform_hint_thirdweb': {
        'uk': 'Thirdweb Batch (Base): lazy mint → secondary на OpenSea/Blur; royalty на рівні контракту.',
        'en': 'Thirdweb Batch (Base): lazy mint → secondary on OpenSea/Blur; contract-level royalties.',
    },
    'qc.item.platform_hint_magic_eden': {
        'uk': 'Magic Eden: після `sugar deploy` — verify колекцію; Launchpad потребує окремої заявки на ME.',
        'en': 'Magic Eden: after `sugar deploy` — verify collection; Launchpad needs a separate ME application.',
    },
    'qc.item.platform_hint_tensor': {
        'uk': 'Tensor: Solana secondary; verify колекцію після мінту для трейдингу (compressed NFT — окремий стандарт).',
        'en': 'Tensor: Solana secondary; verify collection after mint for trading (compressed NFTs use a different standard).',
    },
    'qc.item.platform_hint_sugar_me': {
        'uk': 'Candy Machine → поділіться CM address; ME Launchpad окремо; secondary на ME/Tensor.',
        'en': 'Candy Machine → share CM address; ME Launchpad is separate; secondary on ME/Tensor.',
    },
    'qc.item.platform_hint_w3ir': {
        'uk': 'W3IR ZIP — формат для EVM-платформи, яку **заархівовано** (03.08.2026); живий шлях мінту — Candy Machine, оберіть **Sugar** (приклад: [mint.w3ir.io](https://mint.w3ir.io)).',
        'en': 'W3IR ZIP targets the EVM platform, which is **archived** (2026-08-03); the live mint path is Candy Machine — use the **Sugar** export (example: [mint.w3ir.io](https://mint.w3ir.io)).',
    },
    'qc.item.platform_hint_generic': {
        'uk': 'Generic: передайте ZIP мінтеру або оберіть Thirdweb/OpenSea/Solana до анонсу.',
        'en': 'Generic: hand ZIP to minter or pick Thirdweb/OpenSea/Solana before announce.',
    },
    'qc.item.preflight_clean': {
        'uk': 'Preflight без блокуючих помилок.',
        'en': 'Preflight has no blocking errors.',
    },
    'qc.item.preflight_errors': {
        'uk': '{count} preflight-помилок — виправте перед мінтом (експорт можливий).',
        'en': '{count} preflight errors — fix before mint (export still allowed).',
    },
    'qc.item.symbol_missing': {
        'uk': 'Symbol порожній — Metaplex/Sugar потребують короткий ticker (≤10).',
        'en': 'Symbol is empty — Metaplex/Sugar need a short ticker (≤10).',
    },
    'qc.item.symbol_too_long': {
        'uk': 'Symbol {chars} символів — Metaplex обмежує до 10.',
        'en': 'Symbol is {chars} chars — Metaplex limits to 10.',
    },
    'qc.item.symbol_ok': {
        'uk': 'Symbol «{symbol}» — у межах Metaplex.',
        'en': 'Symbol «{symbol}» — within Metaplex limits.',
    },
    'qc.item.supply_ok': {
        'uk': 'Supply {count} — розумний для indie/PFP дропу.',
        'en': 'Supply {count} — reasonable for an indie/PFP drop.',
    },
    'qc.item.supply_large': {
        'uk': 'Supply {count} — потрібне сильне комʼюніті для sellout.',
        'en': 'Supply {count} — needs strong community for sellout.',
    },
    'qc.item.supply_huge': {
        'uk': 'Supply {count} — дуже високий без великої аудиторії.',
        'en': 'Supply {count} — very high without a large audience.',
    },
    'qc.item.supply_audit_hint': {
        'uk': 'Supply {count} > 500 — розгляньте multisig treasury, audit контракту, поетапний reveal.',
        'en': 'Supply {count} > 500 — consider multisig treasury, contract audit, phased reveal.',
    },
    'qc.item.royalty_ideal': {
        'uk': 'Royalty {pct}% — у рекомендованому діапазоні 5–7.5%.',
        'en': 'Royalty {pct}% — within recommended 5–7.5%.',
    },
    'qc.item.royalty_low': {
        'uk': 'Royalty {pct}% — нижче 5%; ок для mass-market, менше для creator economy.',
        'en': 'Royalty {pct}% — below 5%; OK for mass-market, less for creator revenue.',
    },
    'qc.item.royalty_ok': {
        'uk': 'Royalty {pct}% — прийнятно.',
        'en': 'Royalty {pct}% — acceptable.',
    },
    'qc.item.royalty_high': {
        'uk': 'Royalty {pct}% > 10% — може знизити ліквідність на вторинці.',
        'en': 'Royalty {pct}% > 10% — may reduce secondary liquidity.',
    },
    'qc.item.drop_incomplete': {
        'uk': 'Схвалено {approved}/{planned} — неповний дроп, якщо не навмисно.',
        'en': 'Approved {approved}/{planned} — partial drop unless intentional.',
    },
    'qc.item.drop_complete': {
        'uk': 'Усі заплановані активи схвалені.',
        'en': 'All planned assets are approved.',
    },
    'qc.item.curation_strong': {
        'uk': 'Кураторські оцінки сильні (≥3★).',
        'en': 'Curator ratings are strong (≥3★).',
    },
    'qc.item.curation_weak': {
        'uk': '{count} токенів з низьким рейтингом — перегляньте перед мінтом.',
        'en': '{count} low-rated tokens — review before mint.',
    },
    'qc.item.mint_price_free': {
        'uk': 'Ціна мінту 0 SOL — переконайтесь, що free mint навмисний.',
        'en': 'Mint price 0 SOL — ensure free mint is intentional.',
    },
    'qc.item.mint_price_set': {
        'uk': 'Ціна мінту {price} SOL задана в Guards.',
        'en': 'Mint price set to {price} SOL in Guards.',
    },
    'qc.item.mint_price_high': {
        'uk': 'Ціна мінту {price} SOL — висока для невеликої колекції без hype.',
        'en': 'Mint price {price} SOL — high for a small collection without strong hype.',
    },
    'qc.item.social_discord_ok': {
        'uk': 'Discord — відмічено.',
        'en': 'Discord — checked.',
    },
    'qc.item.social_discord_missing': {
        'uk': 'Немає Discord — зберіть сервер перед анонсом.',
        'en': 'No Discord — set up a server before announce.',
    },
    'qc.item.social_telegram_ok': {
        'uk': 'Telegram — відмічено.',
        'en': 'Telegram — checked.',
    },
    'qc.item.social_telegram_missing': {
        'uk': 'Немає Telegram — додайте канал/чат для анонсів.',
        'en': 'No Telegram — add a channel/chat for announcements.',
    },
    'qc.item.social_twitter_ok': {
        'uk': 'X (Twitter) — відмічено.',
        'en': 'X (Twitter) — checked.',
    },
    'qc.item.social_twitter_missing': {
        'uk': 'Немає X/Twitter — потрібен канал для анонсу.',
        'en': 'No X/Twitter — you need a channel for announcements.',
    },
    'qc.item.social_waitlist_ok': {
        'uk': 'Waitlist/OG — відмічено.',
        'en': 'Waitlist/OG — checked.',
    },
    'qc.item.social_waitlist_missing': {
        'uk': 'Немає waitlist/OG — розгляньте allowlist перед мінтом.',
        'en': 'No waitlist/OG — consider an allowlist before mint.',
    },
    'qc.item.utility_done': {
        'uk': 'Utility/roadmap — відмічено.',
        'en': 'Utility/roadmap — checked.',
    },
    'qc.item.utility_missing': {
        'uk': 'Utility не описано — що отримує власник (мерч, airdrop, IRL)?',
        'en': 'Utility not described — what do holders get (merch, airdrop, IRL)?',
    },
    'qc.item.reveal_done': {
        'uk': 'Reveal plan — відмічено.',
        'en': 'Reveal plan — checked.',
    },
    'qc.item.reveal_missing': {
        'uk': 'Reveal strategy не узгоджена — blind / staged / instant?',
        'en': 'Reveal strategy unclear — blind / staged / instant?',
    },
    'qc.item.seo_keywords': {
        'uk': 'SEO: PFP, generative, utility, 1/1 — у назві/описі/traits без спаму.',
        'en': 'SEO: PFP, generative, utility, 1/1 — in name/description/traits, no spam.',
    },
    'qc.item.rights_attested': {
        'uk': 'Self-attestation: права на контент підтверджено.',
        'en': 'Self-attestation: content rights confirmed.',
    },
    'qc.item.rights_unattested': {
        'uk': 'Права не підтверджено — переконайтесь, що ви автор без чужих брендів.',
        'en': 'Rights not attested — confirm you own the work with no unlicensed brands.',
    },
    'qc.item.policy_reviewed': {
        'uk': 'Політику платформи переглянуто.',
        'en': 'Platform policy reviewed.',
    },
    'qc.item.policy_unreviewed': {
        'uk': 'Політика платформи: без NSFW/hate; для великих дропів — audit/multisig.',
        'en': 'Platform policy: no NSFW/hate; large drops — consider audit/multisig.',
    },
}
