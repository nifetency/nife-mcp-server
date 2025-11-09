#!/bin/bash

# Nife MCP Server - Quick Release Summary
# Shows what's ready and how to release

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get version
VERSION=$(grep "version=" setup.py | cut -d'"' -f2)

echo ""
echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓"
echo "┃  🎉 Nife MCP Server v${VERSION} - Release Status  ┃"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
echo ""

# Check what's ready
echo -e "${BLUE}📦 Package Status${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "dist/nife_mcp_server-${VERSION}-py3-none-any.whl" ]; then
    echo -e "${GREEN}✓${NC} Python wheel built"
else
    echo -e "${RED}✗${NC} Python wheel not found (run: python -m build)"
fi

if [ -f "dist/nife_mcp_server-${VERSION}.tar.gz" ]; then
    echo -e "${GREEN}✓${NC} Source distribution built"
else
    echo -e "${RED}✗${NC} Source distribution not found"
fi

if [ -f "bin/nife-mcp-server.js" ]; then
    echo -e "${GREEN}✓${NC} NPM executable ready"
else
    echo -e "${RED}✗${NC} NPM executable missing"
fi

if [ -f "package.json" ]; then
    echo -e "${GREEN}✓${NC} package.json configured"
else
    echo -e "${RED}✗${NC} package.json missing"
fi

echo ""
echo -e "${BLUE}📄 Documentation Status${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

FILES=("README.md" "LICENSE" "CHANGELOG.md" "RELEASE_GUIDE.md" "setup.py" "pyproject.toml")
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file missing"
    fi
done

echo ""
echo -e "${BLUE}🚀 Quick Release Commands${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${YELLOW}Full Automated Release:${NC}"
echo "  ./release.sh"
echo ""
echo -e "${YELLOW}PyPI Only:${NC}"
echo "  pip install build twine"
echo "  python -m twine upload dist/*"
echo ""
echo -e "${YELLOW}NPM Only:${NC}"
echo "  chmod +x bin/nife-mcp-server.js"
echo "  npm publish --access public"
echo ""
echo -e "${YELLOW}GitHub Only:${NC}"
echo "  git tag -a v${VERSION} -m 'Release v${VERSION}'"
echo "  git push origin v${VERSION}"
echo "  gh release create v${VERSION} --notes-file CHANGELOG.md dist/*"
echo ""

echo -e "${BLUE}📝 Pre-Release Checklist${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [ ] Test installation locally"
echo "  [ ] Test with Claude Desktop"
echo "  [ ] Update CHANGELOG.md"
echo "  [ ] Update README.md"
echo "  [ ] Create GitHub repository"
echo "  [ ] Get PyPI credentials"
echo "  [ ] Get NPM credentials"
echo ""

echo -e "${BLUE}📦 After Publishing${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${GREEN}PyPI:${NC}"
echo "  pip install nife-mcp-server"
echo "  https://pypi.org/project/nife-mcp-server/"
echo ""
echo -e "${GREEN}NPM:${NC}"
echo "  npx @nife/mcp-server"
echo "  https://www.npmjs.com/package/@nife/mcp-server"
echo ""
echo -e "${GREEN}GitHub:${NC}"
echo "  https://github.com/nife-io/nife-mcp-server/releases"
echo ""

echo -e "${BLUE}🎯 Recommended Approach${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Test locally first"
echo "2. Run ./release.sh and choose option 4 (all platforms)"
echo "3. Verify installations work"
echo "4. Announce release"
echo ""

echo -e "${YELLOW}For detailed instructions, see:${NC}"
echo "  📖 RELEASE_GUIDE.md - Complete release guide"
echo "  📊 RELEASE_STATUS.md - Detailed status report"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✨ Ready to release! ✨${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
