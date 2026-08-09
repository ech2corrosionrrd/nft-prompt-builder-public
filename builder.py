"""Чисті функції для побудови промтів і технічних параметрів — без залежностей від Streamlit."""

PLATFORMS: dict[str, dict[str, str]] = {
    "Midjourney v6": {"suffix": "--v 6.0", "ar_flag": "--ar"},
    "Midjourney v7": {"suffix": "--v 7", "ar_flag": "--ar"},
    "Stable Diffusion XL": {"suffix": "", "ar_flag": ""},
    "OpenAI Images": {"suffix": "", "ar_flag": ""},
    "DALL·E 3": {"suffix": "", "ar_flag": ""},  # застаріла назва (збережені проєкти)
    "Leonardo AI": {"suffix": "", "ar_flag": ""},
}


def build_ar_tag(aspect_ratio: str, platform: str) -> str:
    ratio = next(
        (candidate for candidate in ("1:1", "16:9", "4:5", "9:16", "3:4") if candidate in aspect_ratio),
        "1:1",
    )
    ar_flag = PLATFORMS.get(platform, {}).get("ar_flag", "")
    return f"{ar_flag} {ratio}" if ar_flag else f"aspect ratio {ratio}"


def build_tech_params(platform: str, aspect_ratio: str, stylize: int, chaos: int, seed: int) -> str:
    tech = build_ar_tag(aspect_ratio, platform)
    if "Midjourney" in platform:
        tech += f" --s {stylize} --c {chaos} {PLATFORMS[platform]['suffix']}"
        if seed > 0:
            tech += f" --seed {seed}"
    return tech


def build_system_instruction(
    platform: str,
    include_traits: bool,
    include_negative: bool,
    *,
    lang: str = "en",
) -> str:
    """Системний промпт для classic Builder. `lang`: en | uk — мова аналізу в UI."""
    from i18n import trait_categories_en_joined
    from options import TRAIT_CATEGORIES

    cats_uk = ", ".join(TRAIT_CATEGORIES)
    cats_en = trait_categories_en_joined()
    if lang == "uk":
        traits_block = (
            f"\n4. Таблиця Traits (markdown): РІВНО ці категорії — {cats_uk}. "
            "Для кожної — 5–8 варіантів у стовпці або списком."
            if include_traits
            else "\n3. Аналіз шарів (Traits) українською."
        )
        negative_block = (
            "\n5. Negative Prompt (англійською, окремий блок коду)."
            if include_negative
            else ""
        )
        platform_note = {
            "Midjourney v6": "Додай --ar, --s, --v 6.0.",
            "Midjourney v7": "Додай --ar, --s, --v 7.",
            "Stable Diffusion XL": "Позитивний + negative prompt. Без MJ-тегів.",
            "OpenAI Images": "Описовий промт без MJ-тегів.",
            "DALL·E 3": "Описовий промт без MJ-тегів.",
            "Leonardo AI": "Промт + рекомендації Alchemy українською.",
        }.get(platform, "")
        return (
            "Ти — AI Prompt Engineer для генеративних NFT-колекцій.\n"
            f"Платформа: {platform}. {platform_note}\n"
            "Аналіз українською, промти англійською в markdown-блоках коду.\n\n"
            "Структура:\n1. Назва концепту.\n2. Фінальний промт (блок коду).\n"
            f"{traits_block}{negative_block}\n6. Поради щодо узгодженості (2–3 речення)."
        )

    traits_block = (
        f"\n4. Traits markdown table with EXACTLY these category names: {cats_en}. "
        "5–8 variants per category."
        if include_traits
        else "\n3. Trait layer analysis in English."
    )
    negative_block = (
        "\n5. Negative prompt (English, separate fenced code block)."
        if include_negative
        else ""
    )
    platform_note = {
        "Midjourney v6": "Add --ar, --s, --v 6.0.",
        "Midjourney v7": "Add --ar, --s, --v 7.",
        "Stable Diffusion XL": "Positive + negative prompt. No MJ tags.",
        "OpenAI Images": "Descriptive prompt without MJ tags.",
        "DALL·E 3": "Descriptive prompt without MJ tags.",
        "Leonardo AI": "Prompt + Alchemy recommendations in English.",
    }.get(platform, "")
    return (
        "You are an AI prompt engineer for generative NFT collections.\n"
        f"Platform: {platform}. {platform_note}\n"
        "Write analysis and section headings in English; final image prompts in English "
        "inside markdown code fences.\n\n"
        "Structure:\n1. Concept name.\n2. Final prompt (code block).\n"
        f"{traits_block}{negative_block}\n6. Consistency tips (2–3 sentences)."
    )


def build_user_data(
    *,
    idea: str,
    style: str,
    camera: str,
    lighting: str,
    background: str,
    quality: str,
    mood: str,
    platform: str,
    tech: str,
    collection_size: int,
    extra_notes: str,
    lang: str = "en",
) -> str:
    """Текстовий опис налаштувань для LLM (user-повідомлення)."""
    if lang == "uk":
        return f"""
Об'єкт: {idea}
Стиль: {style}
Ракурс: {camera}
Освітлення: {lighting}
Фон: {background}
Якість: {quality}
Настрій: {mood}
Платформа: {platform}
Технічні параметри: {tech}
Розмір колекції: {collection_size}
Побажання: {extra_notes or '—'}
"""
    return f"""
Subject: {idea}
Style: {style}
Camera: {camera}
Lighting: {lighting}
Background: {background}
Detail level: {quality}
Mood: {mood}
Platform: {platform}
Technical params: {tech}
Collection size: {collection_size}
Notes: {extra_notes or '—'}
"""
