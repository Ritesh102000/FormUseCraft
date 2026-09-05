# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Exercise the deployment entrypoint in a fresh interpreter and disposable DB."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_entrypoint_with_serverless_database_connections(postgres_url):
    environment = {
        **os.environ,
        "FORMCRAFT_DATABASE_URL": postgres_url,
        "FORMCRAFT_ROLE": "public",
        "FORMCRAFT_SERVERLESS": "1",
        "FORMCRAFT_GOOGLE_ENABLED": "0",
        "FORMCRAFT_SECRET_KEY": "",
        "FORMCRAFT_ADMIN_PASSWORD_HASH": "",
    }
    code = '''
from fastapi.testclient import TestClient
from index import app
from formcraft import db
with TestClient(app) as client:
    assert client.get("/healthz").json() == {"ok": True}
    assert client.get("/login").status_code == 404
    assert client.get("/admin/new").status_code == 404
    assert client.get("/api/forms").status_code == 404
    assert client.get("/static/form.js").status_code == 200
    assert db.ping()["ready"] is True
'''
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=environment,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_entrypoint_rejects_admin_before_database_connection():
    environment = {
        **os.environ,
        "FORMCRAFT_ROLE": "admin",
        "FORMCRAFT_DATABASE_URL": "",
        "DATABASE_URL": "",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import index"], cwd=ROOT, env=environment,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "Refusing to start" in result.stderr


def test_default_vercel_entrypoint_hosts_owner_dashboard_and_public_forms(postgres_url):
    environment = {
        **os.environ,
        "FORMCRAFT_DATABASE_URL": postgres_url,
        "FORMCRAFT_ADMIN_PASSWORD": "synthetic-owner-password",
        "FORMCRAFT_ADMIN_PASSWORD_HASH": "",
        "FORMCRAFT_SECRET_KEY": "synthetic-long-installation-secret-at-least-32-characters",
        "FORMCRAFT_BASE_URL": "https://forms.example.com",
        "FORMCRAFT_SECURE_COOKIES": "1",
        "FORMCRAFT_GOOGLE_ENABLED": "0",
    }
    environment.pop("FORMCRAFT_ROLE", None)
    code = '''
from fastapi.testclient import TestClient
from index import app
with TestClient(app, base_url="https://forms.example.com") as client:
    assert client.get("/login").status_code == 200
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/healthz").json() == {"ok": True}
    assert client.get("/admin/example/export.csv").status_code == 401
    response = client.post("/login", headers={"Origin": "https://forms.example.com"},
        data={"username":"admin", "password":"synthetic-owner-password"}, follow_redirects=False)
    assert response.status_code == 302
    assert client.get("/").status_code == 200
    assert client.get("/admin/integrations").status_code == 200
'''
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=environment,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
