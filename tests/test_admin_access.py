"""Тести гейту адмін-доступу (ADMIN_WALLETS)."""

from services import admin_access

EVM = "0x" + "ab" * 20
EVM_UPPER = "0x" + "AB" * 20
OTHER = "0x" + "cd" * 20


def test_is_admin_matches_case_insensitive_evm(monkeypatch):
    # У env адреса з ВЕЛИКИМ hex-тілом, перевіряємо нижнім — регістр тіла не важливий.
    monkeypatch.setenv("ADMIN_WALLETS", f"{EVM_UPPER}, {OTHER}")
    assert admin_access.is_admin(EVM)         # 0xab… ↔ 0xAB… (normalize → lower)
    assert admin_access.is_admin(EVM_UPPER)
    assert admin_access.is_admin(OTHER)


def test_non_admin_rejected(monkeypatch):
    monkeypatch.setenv("ADMIN_WALLETS", EVM)
    assert not admin_access.is_admin("0x" + "ef" * 20)
    assert not admin_access.is_admin("")
    assert not admin_access.is_admin(None)


def test_empty_env_no_admins(monkeypatch):
    monkeypatch.delenv("ADMIN_WALLETS", raising=False)
    assert admin_access.admin_wallets() == set()
    assert not admin_access.is_admin(EVM)
