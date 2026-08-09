"""Тести сховища: розмежування історії/проєктів/превʼю/матриць по гаманцю."""

import pytest

import storage

WALLET_A = "0x" + "ab" * 20
WALLET_B = "0x" + "cd" * 20


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path, monkeypatch):
    """Кожен тест — зі своїми теками сховища під tmp_path."""
    monkeypatch.setattr(storage, "HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(storage, "PREVIEWS_DIR", tmp_path / "previews")
    monkeypatch.setattr(storage, "MATRICES_DIR", tmp_path / "matrices")
    monkeypatch.setattr(storage, "BIBLES_DIR", tmp_path / "bibles")


# ── wallet_slug ───────────────────────────────────────────────────────────────

def test_wallet_slug():
    assert storage.wallet_slug("") == "_local"
    assert storage.wallet_slug("   ") == "_local"
    assert storage.wallet_slug(WALLET_A) == WALLET_A  # 0x+hex ФС-безпечні
    sol = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
    assert storage.wallet_slug(sol) == sol  # Solana base58 зберігається
    assert "/" not in storage.wallet_slug("a/b\\c")  # небезпечні символи прибрано


# ── Історія ───────────────────────────────────────────────────────────────────

def test_history_roundtrip_and_isolation():
    storage.save_history(WALLET_A, [{"idea": "a"}])
    storage.save_history(WALLET_B, [{"idea": "b1"}, {"idea": "b2"}])
    assert storage.load_history(WALLET_A) == [{"idea": "a"}]
    assert storage.load_history(WALLET_B) == [{"idea": "b1"}, {"idea": "b2"}]
    assert storage.load_history("0x" + "ef" * 20) == []  # незнайомий — порожньо


def test_history_limit():
    storage.save_history(WALLET_A, [{"n": i} for i in range(80)])
    assert len(storage.load_history(WALLET_A)) == storage.HISTORY_LIMIT


def test_empty_wallet_local_bucket_isolated():
    storage.save_history("", [{"idea": "local"}])
    assert storage.load_history("") == [{"idea": "local"}]
    assert storage.load_history(WALLET_A) == []  # реальний гаманець не бачить _local


# ── Проєкти ───────────────────────────────────────────────────────────────────

def test_projects_isolation():
    storage.save_project(WALLET_A, "proj", {"x": 1})
    assert storage.list_projects(WALLET_A) == ["proj"]
    assert storage.list_projects(WALLET_B) == []           # B не бачить проєкт A
    assert storage.load_project(WALLET_B, "proj") is None   # і не може завантажити
    assert storage.load_project(WALLET_A, "proj") == {"x": 1}
    storage.delete_project(WALLET_A, "proj")
    assert storage.list_projects(WALLET_A) == []


# ── Превʼю ────────────────────────────────────────────────────────────────────

def test_previews_isolation_and_clear():
    a_path = storage.save_preview(WALLET_A, b"a-img", "2026-06-16 12:00:00", "1/2")
    storage.save_preview(WALLET_B, b"b-img", "2026-06-16 12:00:00")
    assert a_path.exists() and a_path.read_bytes() == b"a-img"
    assert len(storage.list_previews(WALLET_A)) == 1
    assert len(storage.list_previews(WALLET_B)) == 1
    # очищення A не чіпає B
    assert storage.clear_previews(WALLET_A) == 1
    assert storage.list_previews(WALLET_A) == []
    assert len(storage.list_previews(WALLET_B)) == 1


# ── Шаблони матриць ──────────────────────────────────────────────────────────

def test_matrices_isolation():
    storage.save_matrix_template(WALLET_A, "m", {"categories": {}})
    assert storage.list_matrix_templates(WALLET_A) == ["m"]
    assert storage.list_matrix_templates(WALLET_B) == []
    assert storage.load_matrix_template(WALLET_B, "m") is None
    assert storage.load_matrix_template(WALLET_A, "m") == {"categories": {}}
    storage.delete_matrix_template(WALLET_A, "m")
    assert storage.list_matrix_templates(WALLET_A) == []


def test_style_bible_isolation_and_roundtrip():
    assert storage.load_style_bible(WALLET_A) == {}
    storage.save_style_bible(WALLET_A, {"style": "pixel art"})
    assert storage.load_style_bible(WALLET_A) == {"style": "pixel art"}
    assert storage.load_style_bible(WALLET_B) == {}  # ізоляція по гаманцю
    storage.clear_style_bible(WALLET_A)
    assert storage.load_style_bible(WALLET_A) == {}
