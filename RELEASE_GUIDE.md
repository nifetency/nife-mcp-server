# Release Guide for Nife MCP Server

This repo ships three artifacts from one version number:

| Artifact | Name | Built from |
|---|---|---|
| PyPI package | `nife-mcp-server` | `pyproject.toml` / `setup.py` |
| NPM wrapper | `@nifelabs/mcp-server` | `package.json`, `bin/nife-mcp-server.js` |
| Container image (hosted connector) | `nife-mcp-server` | `Dockerfile`, see [HOSTED.md](HOSTED.md) |

The NPM package is a thin wrapper: `bin/nife-mcp-server.js` launches
`python -m nife_mcp_server.intelligent_main`, so users need Python 3.10+.

Source repository: https://github.com/nifetency/nife-mcp-server

---

## 1. Bump the version

Keep these in sync:

- `pyproject.toml` (`version`)
- `setup.py` (`version`)
- `package.json` (`version`)
- `src/nife_mcp_server/__init__.py` (`__version__`)

Then add an entry to `CHANGELOG.md` and update `RELEASE_STATUS.md`.

## 2. Test

```bash
pip install -e ".[http]" pytest
pytest
```

CI (`.github/workflows/ci.yml`) lints with flake8, checks imports and builds the
package on Python 3.10 to 3.13 across Linux, macOS and Windows.

## 3. Build

```bash
pip install build twine
rm -rf dist/ build/ *.egg-info/
python -m build
twine check dist/*
```

## 4. Publish

### PyPI

```bash
python -m twine upload dist/*
```

Try TestPyPI first if unsure: `python -m twine upload --repository testpypi dist/*`.

### NPM

```bash
npm login
npm publish --dry-run          # check the file list
npm publish --access public
```

### GitHub release

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --notes-file CHANGELOG.md dist/*
```

### Hosted connector image

```bash
docker build -t nife-mcp-server .
```

Deploy the image behind HTTPS as described in [HOSTED.md](HOSTED.md).

## Automation

- `release.sh` is an interactive wizard for the steps above.
- `.github/workflows/ci.yml`, `publish.yml` and `release.yml` automate testing
  and publishing; check each file for its triggers before tagging.

## Checklist

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for the full pre- and
post-release checklist, and [QUICK_RELEASE.md](QUICK_RELEASE.md) for the short
version.
