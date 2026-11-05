"""OAuth shim tests: discovery, DCR, authorize -> poll -> token with PKCE (backend stubbed)."""
import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("mcp")
pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

from nife_mcp_server import oauth  # noqa: E402
from nife_mcp_server.http_app import app  # noqa: E402

REDIRECT = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


def _jwt(exp):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{b({'alg': 'none'})}.{b({'exp': exp})}.sig"


@pytest.fixture()
def client():
    return TestClient(app)  # no lifespan needed: OAuth routes don't use the MCP session manager


@pytest.fixture()
def backend(monkeypatch):
    state = {"token": ""}

    async def create():
        return "sess-1", "https://app.nife.io/login?id=sess-1"

    async def session_token(sid):
        assert sid == "sess-1"
        return state["token"]

    monkeypatch.setattr(oauth, "_create_session", create)
    monkeypatch.setattr(oauth, "_session_token", session_token)
    return state


def _register(client):
    r = client.post("/register", json={"redirect_uris": [REDIRECT], "client_name": "Claude"})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _authorize(client, cid, **over):
    params = {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT,
              "code_challenge": CHALLENGE, "code_challenge_method": "S256", "state": "xyz"}
    params.update(over)
    return client.get("/authorize", params=params, follow_redirects=False)


def _txn(html):
    return json.loads(html.split("const txn = ")[1].split(";")[0])


def test_discovery(client):
    prm = client.get("/.well-known/oauth-protected-resource").json()
    assert prm["resource"].endswith("/mcp") and prm["authorization_servers"]
    assert client.get("/.well-known/oauth-protected-resource/mcp").status_code == 200
    meta = client.get("/.well-known/oauth-authorization-server").json()
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert meta["token_endpoint"].endswith("/token")


def test_401_advertises_resource_metadata(client):
    r = client.post("/mcp", json={})
    assert r.status_code == 401
    assert "resource_metadata=" in r.headers["www-authenticate"]


def test_expired_jwt_gets_401_invalid_token(client):
    r = client.post("/mcp", headers={"Authorization": f"Bearer {_jwt(time.time() - 10)}"}, json={})
    assert r.status_code == 401
    assert 'error="invalid_token"' in r.headers["www-authenticate"]


def test_register_rejects_foreign_redirect(client):
    r = client.post("/register", json={"redirect_uris": ["https://evil.example/cb"]})
    assert r.status_code == 400 and r.json()["error"] == "invalid_redirect_uri"


def test_full_flow(client, backend):
    cid = _register(client)
    page = _authorize(client, cid)
    assert page.status_code == 200 and "https://app.nife.io/login?id=sess-1" in page.text
    txn = _txn(page.text)

    # user has not signed in yet
    assert client.get("/oauth/poll", params={"txn": txn}).json() == {"pending": True}

    # dashboard completes the cli_session with the user's token
    nife_token = _jwt(time.time() + 3600)
    backend["token"] = nife_token
    redirect = client.get("/oauth/poll", params={"txn": txn}).json()["redirect"]
    sp = urlsplit(redirect)
    assert f"{sp.scheme}://{sp.netloc}{sp.path}" == REDIRECT
    qs = parse_qs(sp.query)
    assert qs["state"] == ["xyz"]

    r = client.post("/token", data={"grant_type": "authorization_code", "code": qs["code"][0],
                                    "redirect_uri": REDIRECT, "client_id": cid, "code_verifier": VERIFIER})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] == nife_token and body["token_type"] == "Bearer"
    assert 0 < body["expires_in"] <= 3600


def test_token_rejects_wrong_verifier(client, backend):
    cid = _register(client)
    txn = _txn(_authorize(client, cid).text)
    backend["token"] = "tok-user-A"
    code = parse_qs(urlsplit(client.get("/oauth/poll", params={"txn": txn}).json()["redirect"]).query)["code"][0]
    r = client.post("/token", data={"grant_type": "authorization_code", "code": code,
                                    "redirect_uri": REDIRECT, "client_id": cid, "code_verifier": "x" * 64})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_authorize_requires_pkce_and_valid_redirect(client, backend):
    cid = _register(client)
    r = _authorize(client, cid, code_challenge_method="plain")
    assert r.status_code == 302 and "error=invalid_request" in r.headers["location"]
    assert _authorize(client, cid, redirect_uri="https://evil.example/cb").status_code == 400
    assert _authorize(client, "garbage").status_code == 400
