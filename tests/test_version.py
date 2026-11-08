"""The package has one version: nife_mcp_server.__version__. Everything else must agree with it."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "nife_mcp_server"


def _declared_version() -> str:
    text = (SRC / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "__init__.py must define __version__"
    return match.group(1)


def test_pyproject_matches():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match and match.group(1) == _declared_version()


def test_setup_py_matches():
    text = (ROOT / "setup.py").read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', text)
    assert match and match.group(1) == _declared_version()


def test_package_json_matches():
    data = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert data["version"] == _declared_version()


def test_hosted_client_uses_the_package_version():
    pytest.importorskip("httpx")
    from nife_mcp_server import __version__, nife_api

    assert nife_api.VERSION == __version__ == _declared_version()


def test_no_module_hardcodes_its_own_version():
    """A literal version in code is how 1.0.4 / 1.2.0 / 2.0.0-intelligent drifted apart."""
    offenders = []
    for path in sorted(SRC.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r'^\s*VERSION\s*=\s*"', text, re.MULTILINE) or "2.0.0-intelligent" in text:
            offenders.append(path.name)
    assert not offenders, f"hard-coded version in: {', '.join(offenders)}"
