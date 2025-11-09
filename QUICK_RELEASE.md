# 🚀 Quick Release Guide - TL;DR

**Everything you need to release in 5 minutes**

---

## ⚡ Super Quick Start

```bash
# 1. Make scripts executable
chmod +x make_executable.sh && ./make_executable.sh

# 2. Check status
./RELEASE_SUMMARY.sh

# 3. Release everything
./release.sh
# Choose option 4 when prompted
```

That's it! 🎉

---

## 📦 What Gets Released

### PyPI (Python Package)
- Package: `nife-mcp-server`
- Install: `pip install nife-mcp-server`
- URL: https://pypi.org/project/nife-mcp-server/

### NPM (Node Package)
- Package: `@nife/mcp-server`
- Install: `npx @nife/mcp-server`
- URL: https://www.npmjs.com/package/@nife/mcp-server

### GitHub (Source)
- Release: `v1.0.0`
- URL: https://github.com/nife-io/nife-mcp-server

---

## 🔑 Requirements

### Before First Release
```bash
# PyPI account
https://pypi.org/account/register/

# NPM account  
https://www.npmjs.com/signup

# GitHub repository
https://github.com/new
```

### Local Setup
```bash
# Install release tools
pip install build twine

# Login to NPM
npm login
```

---

## 📋 Pre-Release Test

```bash
# Test locally
pip install dist/nife_mcp_server-1.0.0-py3-none-any.whl
nife-mcp-server
# Ctrl+C to stop

# Test with Claude
./update_claude_config.sh
# Restart Claude Desktop
```

---

## 🎯 Individual Platform Releases

### PyPI Only
```bash
python -m twine upload dist/*
```

### NPM Only
```bash
npm publish --access public
```

### GitHub Only
```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
gh release create v1.0.0 --notes-file CHANGELOG.md dist/*
```

---

## ✅ After Release

### 1. Verify It Worked
```bash
# PyPI
pip install nife-mcp-server

# NPM
npx @nife/mcp-server

# GitHub
git clone https://github.com/nife-io/nife-mcp-server.git
```

### 2. Test Installation
```bash
# Fresh terminal
pip install nife-mcp-server
nife-mcp-server

# Should start the server!
```

### 3. Update Claude Desktop
```json
{
  "mcpServers": {
    "nife": {
      "command": "npx",
      "args": ["-y", "@nife/mcp-server"],
      "env": {
        "NIFE_ACCESS_TOKEN": "your_token"
      }
    }
  }
}
```

---

## 🐛 Something Wrong?

### Clean Build
```bash
rm -rf dist/ build/ *.egg-info/
python -m build
```

### Test PyPI First
```bash
python -m twine upload --repository testpypi dist/*
```

### NPM Dry Run
```bash
npm publish --dry-run
```

---

## 📢 Announce It!

```bash
# Twitter
🚀 Just released Nife MCP Server v1.0.0!
Easy Claude + Nife.io integration
pip install nife-mcp-server

# Reddit
Posted in r/claudeAI

# LinkedIn
Professional announcement
```

---

## 📚 Need More Info?

- **Detailed Steps**: RELEASE_CHECKLIST.md
- **Full Guide**: RELEASE_GUIDE.md
- **Status Check**: ./RELEASE_SUMMARY.sh
- **Current State**: RELEASE_STATUS.md

---

## 🎊 That's It!

Your Nife MCP Server is now:
- ✅ On PyPI
- ✅ On NPM  
- ✅ On GitHub
- ✅ Ready to use!

**Time to celebrate! 🎉**

---

## 🆘 Quick Troubleshooting

**"Permission denied"**
```bash
chmod +x release.sh
```

**"Module not found"**
```bash
pip install -r requirements.txt
```

**"npm login failed"**
```bash
# Create account first at npmjs.com
npm adduser
```

**"twine: command not found"**
```bash
pip install twine
```

**"gh: command not found"**
```bash
# Install GitHub CLI from cli.github.com
# Or create release manually on GitHub
```

---

## 💡 Pro Tips

1. **Test First**: Always test before releasing
2. **Version Bump**: Increment version for each release
3. **Changelog**: Update CHANGELOG.md every time
4. **Tag It**: Git tags help track releases
5. **Announce**: More visibility = more users

---

## 🎯 Next Release

For v1.0.1 (patch) or v1.1.0 (minor):

```bash
# 1. Update version in:
#    - setup.py
#    - pyproject.toml  
#    - package.json

# 2. Update CHANGELOG.md

# 3. Build and release
python -m build
./release.sh
```

---

**Questions? Issues? Feedback?**

Open an issue on GitHub or check the detailed guides!

Happy releasing! 🚀
