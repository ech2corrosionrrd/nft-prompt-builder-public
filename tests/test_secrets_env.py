"""Тести secrets_env — порожній st.secrets не блокує .env."""

from pathlib import Path

import secrets_env


def test_load_project_env_fills_empty_environ(monkeypatch, tmp_path: Path):
  env_file = tmp_path / ".env"
  env_file.write_text("OPENAI_API_KEY=sk-from-dotenv\n", encoding="utf-8")
  monkeypatch.setattr(secrets_env, "ROOT", tmp_path)
  monkeypatch.setenv("OPENAI_API_KEY", "")

  secrets_env.load_project_env()

  assert secrets_env.get_secret("OPENAI_API_KEY") == "sk-from-dotenv"


def test_load_project_env_does_not_override_nonempty(monkeypatch, tmp_path: Path):
  env_file = tmp_path / ".env"
  env_file.write_text("OPENAI_API_KEY=sk-from-dotenv\n", encoding="utf-8")
  monkeypatch.setattr(secrets_env, "ROOT", tmp_path)
  monkeypatch.setenv("OPENAI_API_KEY", "sk-keep")

  secrets_env.load_project_env()

  assert secrets_env.get_secret("OPENAI_API_KEY") == "sk-keep"


def test_load_project_env_overrides_stale_helio_paylink(monkeypatch, tmp_path: Path):
  """Регресія: st.secrets / старий environ не мають блокувати новий paylink з .env."""
  env_file = tmp_path / ".env"
  env_file.write_text("HELIO_PAYLINK_CREATOR=new-paylink-id\n", encoding="utf-8")
  monkeypatch.setattr(secrets_env, "ROOT", tmp_path)
  monkeypatch.setattr(secrets_env, "_loaded", False)
  monkeypatch.setenv("HELIO_PAYLINK_CREATOR", "old-paylink-id")

  secrets_env.load_project_env()

  assert secrets_env.get_secret("HELIO_PAYLINK_CREATOR") == "new-paylink-id"


def test_force_does_not_clobber_nonpaylink_os_env(monkeypatch, tmp_path: Path):
  """force=True перечитує paylink, але НЕ перебиває непорожній OS-env інших ключів."""
  env_file = tmp_path / ".env"
  env_file.write_text(
    "OPENAI_API_KEY=sk-from-env\nHELIO_PAYLINK_PRO=pro-from-env\n",
    encoding="utf-8",
  )
  monkeypatch.setattr(secrets_env, "ROOT", tmp_path)
  monkeypatch.setattr(secrets_env, "_loaded", False)
  monkeypatch.setenv("OPENAI_API_KEY", "sk-os-wins")
  monkeypatch.setenv("HELIO_PAYLINK_PRO", "pro-os-stale")

  secrets_env.load_project_env(force=True)

  # Звичайний ключ: OS-env лишається джерелом правди.
  assert secrets_env.get_secret("OPENAI_API_KEY") == "sk-os-wins"
  # Paylink: .env завжди перебиває (навіть непорожній OS-env).
  assert secrets_env.get_secret("HELIO_PAYLINK_PRO") == "pro-from-env"
