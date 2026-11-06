"""Repository access checks for GitHub, GitLab and Bitbucket (public and private).

Used by ``inspect_repository`` so a deploy can be validated *before* it starts:
is the repo reachable, is it private, does the branch exist, and which framework
is it. Calls go only to the three fixed provider API hosts (no caller-supplied
hosts, so no SSRF surface) and never carry the caller's Nife token.
"""
import base64
import json
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from nife_mcp_server import site_helpers as h
from nife_mcp_server.nife_api import send

API = {
    "github": "https://api.github.com",
    "gitlab": "https://gitlab.com/api/v4",
    "bitbucket": "https://api.bitbucket.org/2.0",
}


def _headers(provider: str, token: Optional[str]) -> Dict[str, str]:
    hdr = {"Accept": "application/vnd.github+json" if provider == "github" else "application/json"}
    if token:
        if provider == "gitlab":
            hdr["PRIVATE-TOKEN"] = token
        else:
            hdr["Authorization"] = f"Bearer {token}"
    return hdr


def _repo_api(provider: str, owner: str, repo: str) -> str:
    if provider == "github":
        return f"{API['github']}/repos/{owner}/{repo}"
    if provider == "gitlab":
        return f"{API['gitlab']}/projects/{quote(f'{owner}/{repo}', safe='')}"
    return f"{API['bitbucket']}/repositories/{owner}/{repo}"


async def _get(provider, owner, url, token, params=None, extra=None):
    headers = {**_headers(provider, token), **(extra or {})}
    resp = await send("GET", url, params=params, headers=headers, timeout=20.0)
    if provider == "bitbucket" and token and resp.status_code in (401, 403):
        # Older Bitbucket tokens only work with Basic auth (same fallback as the dashboard)
        basic = base64.b64encode(f"{owner}:{token}".encode()).decode()
        resp = await send("GET", url, params=params, headers={"Authorization": f"Basic {basic}"}, timeout=20.0)
    return resp


def _rate_limited(resp) -> bool:
    return resp.status_code in (403, 429) and resp.headers.get("x-ratelimit-remaining") == "0"


def _parse_meta(provider: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if provider == "github":
        return {"private": bool(data.get("private")), "default_branch": data.get("default_branch")}
    if provider == "gitlab":
        return {"private": data.get("visibility") != "public", "default_branch": data.get("default_branch")}
    return {
        "private": bool(data.get("is_private")),
        "default_branch": (data.get("mainbranch") or {}).get("name"),
    }


def _parse_refs(provider: str, data: Any) -> List[str]:
    items = data.get("values", []) if provider == "bitbucket" and isinstance(data, dict) else data
    return [i["name"] for i in items if isinstance(i, dict) and i.get("name")]


async def _package_json(provider, owner, repo, ref, token) -> Optional[Dict[str, Any]]:
    base = _repo_api(provider, owner, repo)
    extra = None
    if provider == "github":
        url, params, extra = f"{base}/contents/package.json", {"ref": ref}, {"Accept": "application/vnd.github.raw+json"}
    elif provider == "gitlab":
        url, params = f"{base}/repository/files/package.json/raw", {"ref": ref}
    else:
        url, params = f"{base}/src/{quote(ref, safe='')}/package.json", None
    resp = await _get(provider, owner, url, token, params=params, extra=extra)
    if resp.status_code != 200:
        return None
    try:
        data = json.loads(resp.text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def inspect_repository(
    repo_url: str,
    *,
    branch: Optional[str],
    ref_type: str = "heads",
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Check repository access and gather deploy hints. ``token`` is the decrypted
    Git token (or None for an anonymous check) and is never included in the result."""
    provider, owner, repo = h.parse_repo_url(repo_url)
    if branch:
        h.validate_branch(branch)
    base = _repo_api(provider, owner, repo)
    notes: List[str] = []
    result: Dict[str, Any] = {
        "provider": provider, "owner": owner, "repo": repo,
        "checked_with_token": bool(token),
    }

    meta_resp = await _get(provider, owner, base, token)
    status = meta_resp.status_code

    if status != 200:
        result.update(accessible=False, visibility="unknown")
        if _rate_limited(meta_resp):
            notes.append(f"The {provider} API rate limit was hit, so access could not be checked. "
                         "Try again later, or deploy directly.")
        elif status in (401, 403):
            result["visibility"] = "private"
            notes.append("The token was rejected or lacks access to this repository." if token
                         else "Authentication is required: this repository is private.")
        elif status == 404:
            result["visibility"] = "private_or_missing"
            notes.append("Repository not found with this token. Check the URL and the token's permissions."
                         if token else
                         "Repository not found. If it is private, pass pat_secret_name (see list_git_secrets).")
        else:
            notes.append(f"The {provider} API returned HTTP {status}.")
        if not token:
            notes.append("A private repository needs pat_secret_name to deploy.")
        result["notes"] = notes
        return result

    try:
        meta = _parse_meta(provider, meta_resp.json())
    except (ValueError, AttributeError, TypeError):
        meta = {"private": None, "default_branch": None}

    result.update(
        accessible=True,
        visibility=("private" if meta["private"] else "public") if meta["private"] is not None else "unknown",
        default_branch=meta["default_branch"],
    )
    if result["visibility"] == "private":
        notes.append("Private repository: deploy_site needs pat_secret_name.")

    # Branches (or tags)
    kind = "tags" if ref_type == "tags" else "branches"
    if provider == "github":
        refs_url, params = f"{base}/{kind}", {"per_page": 100}
    elif provider == "gitlab":
        refs_url, params = f"{base}/repository/{kind}", {"per_page": 100}
    else:
        refs_url, params = f"{base}/refs/{kind}", {"pagelen": 100}
    names: List[str] = []
    refs_resp = await _get(provider, owner, refs_url, token, params=params)
    if refs_resp.status_code == 200:
        try:
            names = _parse_refs(provider, refs_resp.json())
        except (ValueError, TypeError):
            names = []
    result["ref_type"] = "tags" if kind == "tags" else "branches"
    result["refs"] = names[:50]
    result["ref_count"] = len(names)

    effective = branch or meta["default_branch"] or (names[0] if names else None)
    result["branch"] = effective
    if branch:
        result["branch_exists"] = (branch in names) if names else None
        if names and branch not in names:
            notes.append(f"'{branch}' was not found. Available: {', '.join(names[:10])}")

    # Framework detection from package.json
    framework = None
    if effective:
        pkg = await _package_json(provider, owner, repo, effective, token)
        if pkg is not None:
            framework = h.detect_framework(pkg)
            result["has_package_json"] = True
        else:
            result["has_package_json"] = False
            notes.append("No package.json found: likely pre-built static files (or Hugo/Jekyll).")
    result["detected_framework"] = framework
    if framework:
        result["suggested_import_type"] = "source"
        result["suggested_build"] = h.suggested_build(framework)
    else:
        result["suggested_import_type"] = "build" if result.get("has_package_json") is False else None

    result["notes"] = notes
    return result
