"""B1 — тести content-safety блоклиста (ПЛАН_ЗАПОЗИЧЕНЬ.md).

Фільтр увімкнено за замовчуванням (conftest лишає дефолт-on). Перевіряємо:
блок/пропуск, вимкнення, порожнє, двомовність, відсутність хибних спрацювань.
"""

from services import content_safety


# ── Пропуск нормальних промптів (без хибних спрацювань) ───────────────────────

def test_benign_prompt_passes():
    assert content_safety.check_prompt_safety("cyber samurai with plasma katana, neon city").ok


def test_child_word_alone_not_blocked():
    # Саме слово «child» без сексуального маркера НЕ блокується (анти-false-positive).
    assert content_safety.check_prompt_safety("a child playing in a sunny park, cartoon style").ok


def test_nude_adult_art_not_blocked_as_csam():
    # Доросла оголена натура без маркера неповнолітнього не падає в CSAM-категорію.
    res = content_safety.check_prompt_safety("classical nude statue, marble, museum lighting")
    assert res.ok


# ── Блокування недопустимого ──────────────────────────────────────────────────

def test_csam_minor_plus_sexual_blocked():
    res = content_safety.check_prompt_safety("nude child portrait")
    assert not res.ok
    assert res.category == "csam"
    assert res.code == "error.blocked_prompt.csam"


def test_csam_explicit_phrase_blocked():
    assert not content_safety.check_prompt_safety("child porn drawing").ok
    assert not content_safety.check_prompt_safety("pedophile fantasy art").ok


def test_sexual_violence_blocked():
    res = content_safety.check_prompt_safety("scene depicting rape")
    assert not res.ok
    assert res.category == "sexual_violence"


def test_ukrainian_terms_blocked():
    # Двомовність: українські маркери теж ловляться.
    assert not content_safety.check_prompt_safety("оголена дитина, портрет").ok
    assert not content_safety.check_prompt_safety("сцена зґвалтування").ok


# ── Вимкнення / порожнє ───────────────────────────────────────────────────────

def test_disabled_passes_everything(monkeypatch):
    monkeypatch.setenv("CONTENT_SAFETY_ENABLED", "0")
    assert content_safety.check_prompt_safety("child porn").ok  # вимкнено → пропуск


def test_empty_prompt_passes():
    assert content_safety.check_prompt_safety("").ok
    assert content_safety.check_prompt_safety("   ").ok
    assert content_safety.check_prompt_safety(None).ok  # type: ignore[arg-type]


def test_enabled_default_on(monkeypatch):
    monkeypatch.delenv("CONTENT_SAFETY_ENABLED", raising=False)
    assert content_safety.enabled() is True
    monkeypatch.setenv("CONTENT_SAFETY_ENABLED", "0")
    assert content_safety.enabled() is False
    monkeypatch.setenv("CONTENT_SAFETY_ENABLED", "1")
    assert content_safety.enabled() is True


# ── Повідомлення / лог ────────────────────────────────────────────────────────

def test_message_bilingual():
    res = content_safety.check_prompt_safety("nude child")
    assert content_safety.message(res, "uk") != content_safety.message(res, "en")
    assert content_safety.message(res, "uk")  # непорожнє


def test_log_safety_does_not_leak_text(caplog):
    # Landmine: у лог іде лише категорія, не сам заблокований текст.
    res = content_safety.check_prompt_safety("nude child secret_marker_xyz")
    with caplog.at_level("WARNING"):
        content_safety.log_safety(res)
    assert "secret_marker_xyz" not in caplog.text
    assert "csam" in caplog.text


# ── Другий ешелон: OpenAI Moderation API (opt-in, MODERATION_API_ENABLED) ──────

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_post_factory(categories, calls):
    """Фейк requests.post, що повертає задані категорії Moderation API й лічить виклики."""
    def _post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResp({"results": [{"categories": categories}]})
    return _post


def test_moderation_off_by_default_no_network(monkeypatch):
    # Opt-in: без MODERATION_API_ENABLED=1 жодного мережевого виклику немає.
    def _boom(*a, **k):
        raise AssertionError("Moderation API не має викликатися, якщо прапорець вимкнено")
    monkeypatch.setattr(content_safety.requests, "post", _boom)
    assert content_safety.check_prompt_safety("cyber samurai with plasma katana, neon city").ok


def test_moderation_catches_obfuscation_regex_missed(monkeypatch):
    # regex не ловить обфускацію, але Moderation API впевнено позначає sexual/minors.
    monkeypatch.setenv("MODERATION_API_ENABLED", "1")
    monkeypatch.setattr(content_safety, "get_secret", lambda name: "sk-test")
    calls: list = []
    monkeypatch.setattr(content_safety.requests, "post", _fake_post_factory({"sexual/minors": True}, calls))
    res = content_safety.check_prompt_safety("ch1ld er0tica, l33t obfuscation")
    assert not res.ok
    assert res.code == "error.blocked_prompt.csam"
    assert res.category == "csam_moderation"
    assert len(calls) == 1


def test_moderation_allows_legit_art(monkeypatch):
    # sexual (без /minors) НЕ блокуємо — легітимний арт (класична оголена) лишається ok.
    monkeypatch.setenv("MODERATION_API_ENABLED", "1")
    monkeypatch.setattr(content_safety, "get_secret", lambda name: "sk-test")
    monkeypatch.setattr(
        content_safety.requests, "post",
        _fake_post_factory({"sexual/minors": False, "sexual": True}, []),
    )
    assert content_safety.check_prompt_safety("classical nude oil painting, museum lighting").ok


def test_moderation_fail_open_on_network_error(monkeypatch):
    # fail-open: технічний збій провайдера НЕ блокує легітимну генерацію.
    monkeypatch.setenv("MODERATION_API_ENABLED", "1")
    monkeypatch.setattr(content_safety, "get_secret", lambda name: "sk-test")
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(content_safety.requests, "post", _boom)
    assert content_safety.check_prompt_safety("cyber samurai, neon city").ok


def test_moderation_fail_open_without_key(monkeypatch):
    # Немає OPENAI_API_KEY → жодного виклику, fail-open.
    monkeypatch.setenv("MODERATION_API_ENABLED", "1")
    monkeypatch.setattr(content_safety, "get_secret", lambda name: None)
    def _boom(*a, **k):
        raise AssertionError("без ключа не має бути мережевого виклику")
    monkeypatch.setattr(content_safety.requests, "post", _boom)
    assert content_safety.check_prompt_safety("cyber samurai").ok


def test_regex_blocks_before_moderation(monkeypatch):
    # Явний regex-збіг → блок БЕЗ звернення до Moderation API (дешевий перший ешелон).
    monkeypatch.setenv("MODERATION_API_ENABLED", "1")
    monkeypatch.setattr(content_safety, "get_secret", lambda name: "sk-test")
    calls: list = []
    monkeypatch.setattr(content_safety.requests, "post", _fake_post_factory({}, calls))
    res = content_safety.check_prompt_safety("child porn drawing")
    assert not res.ok
    assert res.category == "csam"   # regex-категорія, не moderation
    assert calls == []              # Moderation API не викликано
