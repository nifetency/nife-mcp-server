"""Pure helpers for the site-deploy workflow.

Mirrors the logic in the dashboard's ``DeploySite.tsx`` so a site deployed
through the MCP server behaves exactly like one deployed from the UI.
No network access and no MCP imports here, so it is trivially unit-testable.
"""
import ipaddress
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Same rule the UI enforces (DeploySite.tsx -> validateName)
SITE_NAME_RE = re.compile(r"^([a-z0-9_](?:[a-z0-9_-]{0,28}[a-z0-9])?)$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/@+-]{1,120}$")
REPO_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")

GIT_HOSTS = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "bitbucket.org": "bitbucket",
}

DEFAULT_NODE_VERSION = "20"
SITE_DOMAIN = os.environ.get("NIFE_SITE_DOMAIN", "on.nifetency.com")

# Presets copied from the dashboard's frameworks.json
FRAMEWORKS: Dict[str, Dict[str, str]] = {
    "React": {"install": "npm install", "build": "npm run build", "output": "build"},
    "Vue.js": {"install": "npm install", "build": "npm run build", "output": "dist"},
    "Angular": {"install": "npm install", "build": "ng build", "output": "dist"},
    "Vite": {"install": "npm install", "build": "npm run build", "output": "dist"},
    "Next.js": {
        "install": "npm install",
        "build": "npm run build && npm run export",
        "output": "out",
    },
    "Remix": {"install": "npm install", "build": "npm run build", "output": "public/build"},
    "Svelte": {"install": "npm install", "build": "npm run build", "output": "build"},
    "Ember.js": {"install": "npm install", "build": "npm run build", "output": "dist"},
    "Nuxt.js": {"install": "npm install", "build": "npm run generate", "output": "dist"},
    "Gatsby": {"install": "npm install", "build": "gatsby build", "output": "public"},
    "Hugo": {"install": "", "build": "hugo", "output": "public"},
    "Jekyll": {"install": "bundle install", "build": "jekyll build", "output": "_site"},
}


# ------------------------------------------------------------------ validation
def validate_site_name(name: str) -> str:
    if not isinstance(name, str) or not SITE_NAME_RE.match(name):
        raise ValueError(
            "Invalid site_name. Use 1-30 characters: lowercase letters, digits, "
            "'-' and '_' only, starting and ending with a letter or digit."
        )
    return name


def site_url(name: str) -> str:
    return f"https://{name}.{SITE_DOMAIN}"


def site_host(name: str) -> str:
    """The hostname nifex tracks traffic under for a site."""
    return f"{name}.{SITE_DOMAIN}"


def parse_repo_url(url: str) -> Tuple[str, str, str]:
    """Return (provider, owner, repo) for a GitHub/GitLab/Bitbucket https URL.

    Like the UI, only ``owner/repo`` is supported (no GitLab sub-groups).
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        raise ValueError("repo_url must be an https:// URL")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    provider = GIT_HOSTS.get(host)
    if not provider:
        raise ValueError("repo_url must be a github.com, gitlab.com or bitbucket.org URL")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("repo_url must look like https://github.com/<owner>/<repo>")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not (REPO_SEGMENT_RE.match(owner) and REPO_SEGMENT_RE.match(repo)):
        raise ValueError("repo_url contains invalid characters")
    return provider, owner, repo


def validate_branch(branch: str) -> str:
    if not isinstance(branch, str) or not BRANCH_RE.match(branch) or ".." in branch:
        raise ValueError("Invalid branch/tag name")
    return branch


def build_archive_url(
    provider: str, owner: str, repo: str, branch: str, ref_type: str = "heads"
) -> str:
    """Public-repo archive URL, identical to the UI's construction."""
    validate_branch(branch)
    if provider == "github":
        if ref_type not in ("heads", "tags"):
            raise ValueError("ref_type must be 'heads' or 'tags'")
        return f"https://github.com/{owner}/{repo}/archive/refs/{ref_type}/{branch}.zip"
    if provider == "gitlab":
        return f"https://gitlab.com/{owner}/{repo}/-/archive/{branch}/{repo}-{branch}.zip"
    if provider == "bitbucket":
        return f"https://bitbucket.org/{owner}/{repo}/get/{branch}.zip"
    raise ValueError(f"Unsupported provider: {provider}")


def validate_archive_url(url: str) -> str:
    """Basic SSRF hygiene for caller-supplied archive URLs.

    This cannot catch hostnames that *resolve* to private addresses; the
    backend that downloads the archive remains the real control for that.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("archive_url must be an https:// URL")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
        raise ValueError("archive_url must be a public URL")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    ):
        raise ValueError("archive_url must be a public URL")
    return url.strip()


# ---------------------------------------------------------------- build config
def resolve_build_config(
    framework: Optional[str],
    install_command: Optional[str],
    build_command: Optional[str],
    output_directory: Optional[str],
    node_version: Optional[str],
) -> Dict[str, str]:
    """Merge a framework preset with explicit overrides."""
    preset: Dict[str, str] = {}
    if framework:
        match = next((k for k in FRAMEWORKS if k.lower() == framework.strip().lower()), None)
        if not match:
            raise ValueError(
                f"Unknown framework '{framework}'. Call list_site_frameworks, "
                "or pass build_command and output_directory explicitly."
            )
        preset = FRAMEWORKS[match]

    install = install_command if install_command is not None else preset.get("install", "npm install")
    build = build_command or preset.get("build")
    output = output_directory or preset.get("output")
    if not build or not output:
        raise ValueError(
            "import_type='source' needs a framework, or both build_command and output_directory."
        )
    return {
        "install": install,
        "build": build,
        "output": output,
        "node": (node_version or DEFAULT_NODE_VERSION).strip(),
    }


def build_commands(cfg: Dict[str, str]) -> List[Dict[str, str]]:
    """buildCommandsS3 is positional: [install, build, node version].

    (The third entry is the Node version, not a command: this matches what the
    dashboard sends and what the backend expects.)
    """
    return [{"s3Cmd": cfg["install"]}, {"s3Cmd": cfg["build"]}, {"s3Cmd": cfg["node"]}]


# --------------------------------------------------------------- env variables
def _encryption_key() -> str:
    """The dashboard's VITE_ENCRYPTION_KEY. One key covers env values and vault tokens."""
    return os.environ.get("NIFE_ENCRYPTION_KEY") or os.environ.get("NIFE_ENV_ENCRYPTION_KEY", "")


def decrypt_secret(hex_ciphertext: str, key: Optional[str] = None) -> Optional[str]:
    """Decrypt a vault value (e.g. a stored Git token) the way the dashboard's
    ``decodeAes`` does. Returns None when no key is configured or the value does
    not decrypt, so callers can fall back to anonymous checks.

    The result must never be returned to the model or logged.
    """
    key = key if key is not None else _encryption_key()
    kb = key.encode("utf-8")
    if not key or len(kb) not in (16, 24, 32) or not hex_ciphertext:
        return None
    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        raw = bytes.fromhex(hex_ciphertext.strip())
        dec = Cipher(algorithms.AES(kb), modes.CBC(kb[:16])).decryptor()
        padded = dec.update(raw) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        text = (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
        return text or None
    except Exception:  # wrong key, not hex, bad padding, not utf-8
        return None


def encrypt_env_value(plaintext: str, key: Optional[str] = None) -> str:
    """AES-CBC, key = UTF-8 bytes, IV = first 16 key bytes, hex output.

    Same scheme as the dashboard's ``encryptEnvValue``. If no key is configured
    (``NIFE_ENCRYPTION_KEY`` / ``NIFE_ENV_ENCRYPTION_KEY``) the value is sent as-is,
    which is only acceptable if the backend accepts plaintext over TLS.
    """
    key = key if key is not None else _encryption_key()
    if not key or not plaintext:
        return plaintext
    kb = key.encode("utf-8")
    if len(kb) not in (16, 24, 32):
        raise ValueError("NIFE_ENCRYPTION_KEY must be 16, 24 or 32 bytes long")

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder = padding.PKCS7(128).padder()
    data = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    enc = Cipher(algorithms.AES(kb), modes.CBC(kb[:16])).encryptor()
    return (enc.update(data) + enc.finalize()).hex()


def encode_env(env: Optional[Dict[str, str]]) -> List[Dict[str, str]]:
    if not env:
        return []
    if len(env) > 100:
        raise ValueError("Too many environment variables (max 100)")
    out = []
    for k, v in env.items():
        if not ENV_KEY_RE.match(k):
            raise ValueError(f"Invalid environment variable name: {k!r}")
        if not isinstance(v, str):
            raise ValueError(f"Environment variable {k} must be a string")
        if len(v) > 8192:
            raise ValueError(f"Environment variable {k} is too long")
        out.append({"name": k, "value": encrypt_env_value(v)})
    return out


# -------------------------------------------------------- framework detection
# Priority-ordered dependency -> framework (names match FRAMEWORKS). Same rules as the
# dashboard's one-click-deploy flow in DeploySite.tsx.
DEP_RULES = [
    (["next"], "Next.js"),
    (["nuxt", "nuxt3", "@nuxt/core"], "Nuxt.js"),
    (["gatsby"], "Gatsby"),
    (["@remix-run/dev", "@remix-run/react"], "Remix"),
    (["@sveltejs/kit", "svelte"], "Svelte"),
    (["@angular/core"], "Angular"),
    (["ember-cli"], "Ember.js"),
    (["vue"], "Vue.js"),
    (["vite"], "Vite"),
    (["react", "react-dom", "react-scripts"], "React"),
]


def detect_framework(package_json: Dict[str, Any]) -> Optional[str]:
    deps: Dict[str, Any] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        value = package_json.get(section)
        if isinstance(value, dict):
            deps.update(value)
    for names, framework in DEP_RULES:
        if any(n in deps for n in names):
            return framework
    return None


def suggested_build(framework: str) -> Dict[str, str]:
    p = FRAMEWORKS[framework]
    return {
        "framework": framework,
        "install_command": p["install"],
        "build_command": p["build"],
        "output_directory": p["output"],
    }


# Vault secret types that can hold a token for each Git provider (as the UI filters them)
PROVIDER_SECRET_TYPES = {
    "github": ("PAT", "GitHub", "github_registry"),
    "gitlab": ("PAT", "gitlab_registry", "GitLab"),
    "bitbucket": ("PAT", "bitbucket_registry", "Bitbucket"),
}


def secret_matches_provider(registry_type: Optional[str], provider: str) -> bool:
    return not registry_type or registry_type in PROVIDER_SECRET_TYPES.get(provider, ())


# ------------------------------------------------------ analytics formatting
RANGE_HOURS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}


def validate_range(value: str) -> str:
    if value not in RANGE_HOURS:
        raise ValueError("range must be one of: " + ", ".join(RANGE_HOURS))
    return value


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def build_seconds(raw: Any) -> Optional[int]:
    """The dashboard treats buildTime as milliseconds."""
    try:
        return round(int(float(raw)) / 1000)
    except (TypeError, ValueError):
        return None


def parse_build_commands(cmds: Optional[List[Dict[str, str]]]) -> Optional[Dict[str, str]]:
    """buildCommandsS3 is positional: [install, build, node version]."""
    values = [c.get("s3Cmd", "") for c in (cmds or []) if isinstance(c, dict)]
    if len(values) < 2:
        return None
    out = {"install_command": values[0], "build_command": values[1]}
    if len(values) > 2:
        out["node_version"] = values[2]
    return out


def gb(value: Any) -> Optional[float]:
    """Decimal GB (10^9), the unit the backend bills bandwidth in."""
    try:
        return round(float(value) / 1_000_000_000, 3)
    except (TypeError, ValueError):
        return None


def top_items(value: Any, n: int = 10) -> Any:
    """Keep analytics payloads small: top-n of a {name: number} map, else truncate."""
    if isinstance(value, dict):
        numeric = {k: v for k, v in value.items() if isinstance(v, (int, float))}
        if numeric:
            ranked = sorted(numeric.items(), key=lambda kv: kv[1], reverse=True)[:n]
            return [{"name": k, "value": v} for k, v in ranked]
        return dict(list(value.items())[:n])
    if isinstance(value, list):
        return value[:n]
    return value


def downsample_series(points: List[Dict[str, Any]], max_points: int = 24) -> List[Dict[str, Any]]:
    """Collapse a nifex time series into at most ``max_points`` buckets."""
    if not points:
        return []
    size = max(1, -(-len(points) // max_points))  # ceil
    out = []
    for i in range(0, len(points), size):
        chunk = points[i:i + size]
        req = sum(int(p.get("requests") or 0) for p in chunk)
        weighted = sum((p.get("avg_ms") or 0) * int(p.get("requests") or 0) for p in chunk)
        p95s = [p["p95_ms"] for p in chunk if p.get("p95_ms") is not None]
        out.append({
            "time": chunk[0].get("time"),
            "requests": req,
            "errors_5xx": sum(int(p.get("s5xx") or 0) for p in chunk),
            "errors_4xx": sum(int(p.get("s4xx") or 0) for p in chunk),
            "avg_ms": round(weighted / req, 1) if req else None,
            "p95_ms_max": max(p95s) if p95s else None,
            "bytes_out": sum(int(p.get("bytes_out") or 0) for p in chunk),
        })
    return out


def uptime_stats(beats: List[Dict[str, Any]], max_incidents: int = 5) -> Dict[str, Any]:
    """Availability from Uptime Kuma heartbeats: share of checks that were up, the
    average response time, and the most recent outages."""
    ordered = sorted(beats, key=lambda b: str(b.get("time", "")))
    total = len(ordered)
    if total == 0:
        return {"checks": 0, "uptime_percent": None}
    up = sum(1 for b in ordered if b.get("status") is True)
    pings = [b["ping"] for b in ordered if isinstance(b.get("ping"), (int, float)) and b["ping"] > 0]

    incidents: List[Dict[str, Any]] = []
    run: List[Dict[str, Any]] = []
    for b in ordered + [{"status": True}]:  # sentinel closes a trailing outage
        if b.get("status") is True:
            if run:
                incidents.append({"from": run[0].get("time"), "to": run[-1].get("time"), "failed_checks": len(run)})
                run = []
        else:
            run.append(b)
    last = ordered[-1]
    return {
        "checks": total,
        "uptime_percent": round(up / total * 100, 2),
        "avg_response_ms": round(sum(pings) / len(pings)) if pings else None,
        "currently_up": last.get("status") is True,
        "last_check": last.get("time"),
        "outages": len(incidents),
        "recent_outages": incidents[-max_incidents:],
    }
