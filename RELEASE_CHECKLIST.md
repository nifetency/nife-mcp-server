# 🎯 Final Release Checklist

Use this checklist before releasing your Nife MCP Server.

---

## 🔍 Pre-Release Verification

### Environment Setup
- [ ] Python 3.10+ installed and working
- [ ] Node.js 16+ installed (for NPM release)
- [ ] Git installed and configured
- [ ] PyPI account created (https://pypi.org/account/register/)
- [ ] NPM account created (https://www.npmjs.com/signup)
- [ ] GitHub repository created (if releasing to GitHub)

### Local Testing
- [ ] Run `./RELEASE_SUMMARY.sh` to verify package status
- [ ] Test Python package locally:
  ```bash
  pip install dist/nife_mcp_server-1.0.4-py3-none-any.whl
  nife-mcp-server
  pip uninstall nife-mcp-server
  ```
- [ ] Test NPM package locally:
  ```bash
  npm install -g .
  nife-mcp-server
  npm uninstall -g @nifelabs/mcp-server
  ```
- [ ] Test with Claude Desktop (update config, restart Claude)
- [ ] Verify all GraphQL queries work
- [ ] Check error handling
- [ ] Verify authentication works

### Files Verification
- [ ] All version numbers updated to 1.0.4 (setup.py, pyproject.toml, package.json, src/nife_mcp_server/__init__.py)
- [ ] README.md is accurate and complete
- [ ] CHANGELOG.md has release notes
- [ ] LICENSE file is present
- [ ] .gitignore excludes unnecessary files
- [ ] All scripts are executable (`chmod +x *.sh`)

---

## 🚀 Release Steps

### Step 1: Make Scripts Executable
```bash
chmod +x make_executable.sh
./make_executable.sh
```

### Step 2: Run Release Summary
```bash
./RELEASE_SUMMARY.sh
```

Review the output and ensure everything is ✓

### Step 3: Choose Release Method

#### Option A: Automated Release (Recommended)
```bash
./release.sh
```

Select option 4 (All platforms) when prompted.

#### Option B: Manual Release

**PyPI:**
```bash
pip install build twine
python -m twine upload dist/*
```

**NPM:**
```bash
npm login
npm publish --access public
```

**GitHub:**
```bash
git tag -a v1.0.4 -m "Release v1.0.4"
git push origin v1.0.4
gh release create v1.0.4 --notes-file CHANGELOG.md dist/*
```

---

## ✅ Post-Release Verification

### Verify PyPI Release
- [ ] Visit https://pypi.org/project/nife-mcp-server/
- [ ] Package appears in search
- [ ] Version 1.0.4 is listed
- [ ] README renders correctly
- [ ] Test installation:
  ```bash
  pip install nife-mcp-server
  nife-mcp-server --help
  ```

### Verify NPM Release
- [ ] Visit https://www.npmjs.com/package/@nifelabs/mcp-server
- [ ] Package appears in search
- [ ] Version 1.0.4 is listed
- [ ] README displays correctly
- [ ] Test installation:
  ```bash
  npx @nifelabs/mcp-server
  ```

### Verify GitHub Release
- [ ] Visit https://github.com/nifetency/nife-mcp-server/releases
- [ ] Release v1.0.4 is visible
- [ ] CHANGELOG.md is in release notes
- [ ] Distribution files are attached
- [ ] Test cloning and installation:
  ```bash
  git clone https://github.com/nifetency/nife-mcp-server.git
  cd nife-mcp-server
  pip install -r requirements.txt
  python -m nife_mcp_server.intelligent_main
  ```

---

## 📢 Announcement

### Documentation
- [ ] Update main website (if exists)
- [ ] Update Nife.io documentation
- [ ] Add to MCP servers list
- [ ] Create usage examples
- [ ] Record demo video (optional)

### Social Media
- [ ] Twitter/X announcement
- [ ] LinkedIn post
- [ ] Reddit r/claudeAI post
- [ ] Dev.to article
- [ ] Hacker News Show HN (optional)

### Community
- [ ] Announce in Nife.io community
- [ ] Post in MCP community forums
- [ ] Email newsletter (if applicable)
- [ ] Slack/Discord announcement

---

## 📝 Announcement Templates

### Twitter/X
```
🚀 Excited to announce Nife MCP Server v1.0.4!

A Model Context Protocol server for @nife_io's GraphQL API.

✨ Features:
- Auto-discovery of GraphQL schema
- Dynamic tool generation
- Zero hardcoded queries
- Easy Claude Desktop integration

Install: pip install nife-mcp-server

#MCP #AI #Claude #GraphQL
```

### Dev.to Article Structure
```markdown
# Introducing Nife MCP Server v1.0.4

[Introduction about MCP and Nife.io]

## What is it?
[Explain the project]

## Key Features
- Intelligent schema discovery
- Dynamic tool generation
- Multiple installation methods

## Installation
[Show installation commands]

## Usage with Claude Desktop
[Show configuration]

## Try it out!
[Call to action]
```

### Reddit r/claudeAI
```
[Project] Nife MCP Server v1.0.4 - GraphQL API Integration

I've released an MCP server that connects Claude to the Nife.io GraphQL API 
with intelligent schema discovery and dynamic tool generation.

Features:
- Auto-discovers GraphQL schema
- Generates MCP tools dynamically
- Easy Claude Desktop integration
- Multiple installation options

Installation:
pip install nife-mcp-server

GitHub: https://github.com/nifetency/nife-mcp-server
PyPI: https://pypi.org/project/nife-mcp-server/

Would love feedback from the community!
```

---

## 🐛 Issue Management

### Setup Issue Templates
Issue templates live in `.github/ISSUE_TEMPLATE/`:
- [x] bug_report.yml
- [x] feature_request.yml
- [x] question.yml

### Monitor Issues
- [ ] Check GitHub issues daily (first week)
- [ ] Respond within 24 hours
- [ ] Label issues appropriately
- [ ] Create milestones for fixes

### Bug Fix Process
1. Acknowledge issue
2. Reproduce locally
3. Create fix branch
4. Test thoroughly
5. Release patch version
6. Update CHANGELOG.md

---

## 📊 Metrics to Track

### Week 1
- [ ] Download counts (PyPI + NPM)
- [ ] GitHub stars/forks
- [ ] Issue reports
- [ ] Social media engagement
- [ ] User feedback

### Month 1
- [ ] Active users
- [ ] Feature requests
- [ ] Contribution activity
- [ ] Documentation traffic
- [ ] Search rankings

---

## 🔄 Next Version Planning

### Gather Feedback
- [ ] Review user issues
- [ ] Analyze usage patterns
- [ ] Collect feature requests
- [ ] Identify pain points

### Plan v1.1.0
- [ ] Prioritize features
- [ ] Create roadmap
- [ ] Update GitHub Projects
- [ ] Set release date

---

## 🎉 Success Criteria

Your release is successful when:

- ✅ Package installs without errors
- ✅ Works with Claude Desktop
- ✅ Users can complete basic tasks
- ✅ Documentation is clear
- ✅ No critical bugs reported
- ✅ Community engagement is positive

---

## 🆘 Rollback Plan

If something goes wrong:

### PyPI
```bash
# Cannot delete from PyPI, but can yank version
# twine has no yank command: yank the release from the project's
# "Manage" page on pypi.org (release 1.0.4 -> Options -> Yank)
```

### NPM
```bash
# Unpublish within 72 hours
npm unpublish @nifelabs/mcp-server@1.0.4
```

### GitHub
```bash
# Delete release
gh release delete v1.0.4
git push origin :refs/tags/v1.0.4
```

---

## 📞 Support Channels

Make sure these are ready:
- [ ] GitHub Issues enabled
- [ ] Email support active
- [ ] Community forum access
- [ ] Documentation site live

---

## ✨ Final Checklist

Before hitting publish:

- [ ] ✅ All tests pass
- [ ] ✅ Documentation complete
- [ ] ✅ Version numbers correct
- [ ] ✅ CHANGELOG.md updated
- [ ] ✅ Scripts executable
- [ ] ✅ Local testing done
- [ ] ✅ Credentials ready
- [ ] ✅ Announcement draft ready
- [ ] ✅ Support channels active
- [ ] ✅ Rollback plan understood

---

## 🎊 You're Ready!

When all checkboxes above are ✓, you're ready to release!

Run: `./release.sh` and follow the prompts.

**Good luck! 🚀**

---

**Questions?**
- Read RELEASE_GUIDE.md
- Check RELEASE_STATUS.md
- Run ./RELEASE_SUMMARY.sh
- Open a GitHub issue

**Remember:** It's okay if v1.0.0 isn't perfect. You can always release v1.0.1 with fixes!
