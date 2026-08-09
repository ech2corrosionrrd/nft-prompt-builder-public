"""Тести workspace_limits: квоти проєктів і диска на гаманець."""

from __future__ import annotations

import pytest

from services import payment_service, project_service, workspace_limits

W1 = "0x" + "a001" * 10
W2 = "0x" + "a002" * 10
W3 = "0x" + "a003" * 10
W4 = "0x" + "a004" * 10
W5 = "0x" + "a005" * 10
W6 = "0x" + "a006" * 10


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Кожен тест — зі своєю чистою users.db (як test_payments / test_freemium)."""
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


@pytest.fixture
def mock_st_session(monkeypatch):
    class _State(dict):
        def get(self, key, default=None):
            return super().get(key, default)

        def pop(self, key, default=None):
            return super().pop(key, default)

    sess = _State()
    monkeypatch.setattr(project_service.st, "session_state", sess)
    return sess


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(workspace_limits, "WORKSPACE_ROOT", root)
    monkeypatch.setattr(project_service, "WORKSPACE_ROOT", root)
    return root


def test_defaults_unlimited(monkeypatch):
    monkeypatch.delenv("WORKSPACE_MAX_PROJECTS_PER_WALLET", raising=False)
    monkeypatch.delenv("WORKSPACE_MAX_MB_PER_WALLET", raising=False)
    assert workspace_limits.max_projects_limit() == 0
    assert workspace_limits.max_mb_limit() == 0
    assert workspace_limits.warn_project_count() == 15


def test_project_limit_blocks_free_wallet(monkeypatch, workspace, mock_st_session):
    monkeypatch.setenv("WORKSPACE_MAX_PROJECTS_PER_WALLET", "2")
    project_service.create_project(W1, "One")
    project_service.create_project(W1, "Two")
    with pytest.raises(workspace_limits.ProjectQuotaError) as exc:
        workspace_limits.assert_can_add(W1)
    assert exc.value.code == "project_limit"


def test_project_limit_skipped_for_purchased(monkeypatch, workspace, mock_st_session):
    monkeypatch.setenv("WORKSPACE_MAX_PROJECTS_PER_WALLET", "1")
    project_service.create_project(W2, "One")
    payment_service.record_payment("tx-ws-2", W2, 100, 4.99)
    workspace_limits.assert_can_add(W2)


def test_mb_limit_blocks_duplicate(monkeypatch, workspace, mock_st_session):
    monkeypatch.setenv("WORKSPACE_MAX_MB_PER_WALLET", "1")
    pid = project_service.create_project(W3, "Big")
    assets = project_service.assets_dir(W3, pid)
    project_service.write_asset(assets, b"x" * 900_000)
    with pytest.raises(workspace_limits.ProjectQuotaError) as exc:
        workspace_limits.assert_can_add(W3, extra_projects=1, extra_bytes=900_000)
    assert exc.value.code == "disk_limit"


def test_quota_status_show_warn(monkeypatch, workspace, mock_st_session):
    monkeypatch.setenv("WORKSPACE_PROJECT_WARN_COUNT", "3")
    project_service.create_project(W4, "One")
    project_service.create_project(W4, "Two")
    assert not workspace_limits.quota_status(W4)["show_warn"]
    project_service.create_project(W4, "Three")
    assert workspace_limits.quota_status(W4)["show_warn"]


def test_create_project_respects_limit(monkeypatch, workspace, mock_st_session):
    monkeypatch.setenv("WORKSPACE_MAX_PROJECTS_PER_WALLET", "1")
    project_service.create_project(W5, "One")
    with pytest.raises(workspace_limits.ProjectQuotaError):
        project_service.create_project(W5, "Two")


def test_host_summary(workspace, mock_st_session):
    project_service.create_project(W6, "A")
    summary = workspace_limits.host_summary()
    assert summary["wallet_count"] >= 1
    assert summary["total_bytes"] > 0


def test_quota_status_skips_disk_walk_when_mb_off(monkeypatch, workspace, mock_st_session):
    """Fix 1: при вимкненому MB-ліміті обсяг не рахуємо (perf: без rglob на rerun)."""
    monkeypatch.delenv("WORKSPACE_MAX_MB_PER_WALLET", raising=False)
    pid = project_service.create_project(W1, "One")
    project_service.write_asset(project_service.assets_dir(W1, pid), b"x" * 500_000)
    called = False

    def _spy(_wallet):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(workspace_limits, "wallet_bytes", _spy)
    status = workspace_limits.quota_status(W1)
    assert called is False, "wallet_bytes не має викликатись при вимкненому MB-ліміті"
    assert status["used_bytes"] == 0


def test_quota_status_computes_disk_when_mb_on(monkeypatch, workspace, mock_st_session):
    """Дзеркало: при заданому MB-ліміті обсяг рахується (інакше assert не працює)."""
    monkeypatch.setenv("WORKSPACE_MAX_MB_PER_WALLET", "10")
    pid = project_service.create_project(W2, "One")
    project_service.write_asset(project_service.assets_dir(W2, pid), b"x" * 500_000)
    status = workspace_limits.quota_status(W2)
    assert status["used_bytes"] >= 500_000


def test_quota_status_skips_db_when_project_limit_off(monkeypatch, workspace, mock_st_session):
    """Fix 1: при вимкненому ліміті кількості — без хіту в БД (_has_purchased)."""
    monkeypatch.delenv("WORKSPACE_MAX_PROJECTS_PER_WALLET", raising=False)
    project_service.create_project(W3, "One")

    def _boom(_wallet):
        raise AssertionError("_has_purchased не має викликатись при вимкненому ліміті")

    monkeypatch.setattr(workspace_limits, "_has_purchased", _boom)
    status = workspace_limits.quota_status(W3)
    assert status["purchased"] is False


def test_project_disk_stats_counts_files(workspace):
    proj = workspace / "w1" / "proj1"
    proj.mkdir(parents=True)
    (proj / "manifest.json").write_bytes(b"{}")
    assets = proj / "assets"
    assets.mkdir()
    (assets / "a.png").write_bytes(b"x" * 100)
    stats = workspace_limits.project_disk_stats(proj)
    assert stats["bytes"] >= 100
    assert stats["files"] == 2
