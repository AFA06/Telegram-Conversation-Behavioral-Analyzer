"""Regression tests for the SPA fallback routing fix.

Reported directly by the user: dashboard "sections" appeared broken. Traced
to the deployed server only ever serving the built frontend correctly for
"/" — any other route (as Telegram's Mini App WebView reloads at whenever
it's backgrounded and reopened) 404'd, because a plain
StaticFiles(html=True) mount has no concept of client-side routes.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_unmatched_path_404s_when_no_frontend_build_exists(monkeypatch):
    """Local dev without `npm run build` (or a fresh checkout in CI) must
    keep 404ing for non-API paths, not error out or serve something wrong.
    """
    import app.main as main_module

    monkeypatch.setattr(main_module, "_FRONTEND_DIST", Path("/nonexistent-build-dir"))
    monkeypatch.setattr(main_module, "_INDEX_HTML", Path("/nonexistent-build-dir/index.html"))

    with TestClient(app) as client:
        resp = client.get("/activity")
        assert resp.status_code == 404


@pytest.fixture()
def fake_frontend_build(tmp_path, monkeypatch):
    import app.main as main_module

    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>the spa shell</body></html>")
    (assets / "app-abc123.js").write_text("console.log('app');")

    monkeypatch.setattr(main_module, "_FRONTEND_DIST", dist)
    monkeypatch.setattr(main_module, "_INDEX_HTML", dist / "index.html")
    yield dist


@pytest.mark.parametrize("path", ["/", "/activity", "/responses", "/conversations", "/calendar", "/trends", "/explorer", "/settings"])
def test_every_dashboard_route_serves_the_spa_shell(fake_frontend_build, path):
    with TestClient(app) as client:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}, not the SPA shell"
        assert "the spa shell" in resp.text


def test_spa_shell_is_never_cached(fake_frontend_build):
    """A cached index.html points the browser/WebView at a stale, possibly
    no-longer-existing hashed JS bundle after a real deploy — exactly what
    would make a genuine fix look like "still showing the old version".
    """
    with TestClient(app) as client:
        resp = client.get("/activity")
        assert resp.headers.get("cache-control") == "no-store"


def test_real_built_asset_is_served_directly_not_as_spa_shell(fake_frontend_build):
    with TestClient(app) as client:
        resp = client.get("/assets/app-abc123.js")
        assert resp.status_code == 200
        assert "console.log" in resp.text


def test_head_request_is_supported_not_405(fake_frontend_build):
    """Render's own platform health probe sent HEAD / — a GET-only route
    returned 405, which risks the platform treating a genuinely healthy
    deploy as unhealthy.
    """
    with TestClient(app) as client:
        resp = client.request("HEAD", "/")
        assert resp.status_code == 200


def test_api_and_telegram_paths_are_not_swallowed_by_the_spa_fallback(fake_frontend_build):
    with TestClient(app) as client:
        assert client.get("/api/totally-made-up-endpoint").status_code == 404
        assert client.get("/telegram/totally-made-up-endpoint").status_code == 404
        # a real API route must still work normally alongside the fallback
        assert client.get("/api/health").status_code == 200
