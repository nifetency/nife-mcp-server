import pytest

from nife_mcp_server import site_helpers as h


def test_site_name_validation():
    for ok in ["a", "my-site", "awesome-site-1234", "a_b", "x" * 30]:
        assert h.validate_site_name(ok) == ok
    for bad in ["", "-a", "a-", "My-Site", "a b", "x" * 31, "a.b", "../x"]:
        with pytest.raises(ValueError):
            h.validate_site_name(bad)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/acme/web", ("github", "acme", "web")),
        ("https://github.com/acme/web.git", ("github", "acme", "web")),
        ("https://www.github.com/acme/web/tree/main", ("github", "acme", "web")),
        ("https://gitlab.com/acme/web", ("gitlab", "acme", "web")),
        ("https://bitbucket.org/acme/web", ("bitbucket", "acme", "web")),
    ],
)
def test_parse_repo_url(url, expected):
    assert h.parse_repo_url(url) == expected


@pytest.mark.parametrize(
    "url",
    ["http://github.com/a/b", "https://evil.com/a/b", "https://github.com/a", "ftp://github.com/a/b"],
)
def test_parse_repo_url_rejects(url):
    with pytest.raises(ValueError):
        h.parse_repo_url(url)


def test_archive_urls_match_ui():
    assert h.build_archive_url("github", "o", "r", "main", "heads") == "https://github.com/o/r/archive/refs/heads/main.zip"
    assert h.build_archive_url("github", "o", "r", "v1.0", "tags") == "https://github.com/o/r/archive/refs/tags/v1.0.zip"
    assert h.build_archive_url("gitlab", "o", "r", "main") == "https://gitlab.com/o/r/-/archive/main/r-main.zip"
    assert h.build_archive_url("bitbucket", "o", "r", "main") == "https://bitbucket.org/o/r/get/main.zip"


@pytest.mark.parametrize("branch", ["", "a b", "a;b", "../x", "x" * 200, "a\nb"])
def test_bad_branch_rejected(branch):
    with pytest.raises(ValueError):
        h.validate_branch(branch)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/a.zip",
        "https://localhost/a.zip",
        "https://127.0.0.1/a.zip",
        "https://10.0.0.5/a.zip",
        "https://169.254.169.254/latest",
        "https://db.internal/a.zip",
    ],
)
def test_archive_url_rejects_private(url):
    with pytest.raises(ValueError):
        h.validate_archive_url(url)


def test_archive_url_accepts_public():
    assert h.validate_archive_url("https://example.com/site.zip") == "https://example.com/site.zip"


def test_build_config_from_preset_and_overrides():
    cfg = h.resolve_build_config("react", None, None, None, None)
    assert cfg == {"install": "npm install", "build": "npm run build", "output": "build", "node": "20"}
    cfg = h.resolve_build_config("Vite", "pnpm install", None, "out", "18")
    assert cfg["install"] == "pnpm install" and cfg["output"] == "out" and cfg["node"] == "18"
    # Hugo has an empty install command, which must be preserved
    assert h.resolve_build_config("Hugo", None, None, None, None)["install"] == ""


def test_build_config_errors():
    with pytest.raises(ValueError):
        h.resolve_build_config("nonexistent", None, None, None, None)
    with pytest.raises(ValueError):
        h.resolve_build_config(None, None, None, None, None)
    # no framework but explicit build+output is fine
    assert h.resolve_build_config(None, None, "make", "public", None)["build"] == "make"


def test_build_commands_are_positional_with_node_last():
    cfg = {"install": "npm install", "build": "npm run build", "output": "dist", "node": "20"}
    assert h.build_commands(cfg) == [
        {"s3Cmd": "npm install"}, {"s3Cmd": "npm run build"}, {"s3Cmd": "20"}
    ]


def test_env_plaintext_when_no_key(monkeypatch):
    monkeypatch.delenv("NIFE_ENV_ENCRYPTION_KEY", raising=False)
    assert h.encode_env({"API_URL": "https://x"}) == [{"name": "API_URL", "value": "https://x"}]


def test_env_encrypts_with_key(monkeypatch):
    monkeypatch.setenv("NIFE_ENV_ENCRYPTION_KEY", "0123456789abcdef")
    out = h.encode_env({"A": "secret"})
    assert out[0]["value"] != "secret"
    int(out[0]["value"], 16)  # hex


def test_env_rejects_bad_input(monkeypatch):
    with pytest.raises(ValueError):
        h.encode_env({"bad name": "x"})
    with pytest.raises(ValueError):
        h.encode_env({"A": "x" * 9000})
    monkeypatch.setenv("NIFE_ENV_ENCRYPTION_KEY", "short")
    with pytest.raises(ValueError):
        h.encode_env({"A": "x"})
