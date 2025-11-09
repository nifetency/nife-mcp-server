#!/bin/bash

# Nife MCP Server - Quick Release Script

set -e

echo "🚀 Nife MCP Server Release Script"
echo "=================================="
echo ""

# Check if we're in the right directory
if [ ! -f "setup.py" ]; then
    echo "❌ Error: Must be run from nife-mcp-server root directory"
    exit 1
fi

# Get version
VERSION=$(grep "version=" setup.py | cut -d'"' -f2)
echo "📦 Version: $VERSION"
echo ""

# Menu
echo "Select release target:"
echo "1. PyPI (Python Package Index)"
echo "2. NPM (Node Package Manager)"
echo "3. GitHub Release"
echo "4. All of the above"
echo "5. Test builds only (no publish)"
echo ""
read -p "Enter choice (1-5): " choice

case $choice in
    1)
        echo "📦 Publishing to PyPI..."
        ;;
    2)
        echo "📦 Publishing to NPM..."
        ;;
    3)
        echo "📦 Creating GitHub Release..."
        ;;
    4)
        echo "📦 Publishing everywhere..."
        ;;
    5)
        echo "🧪 Test mode - building only..."
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "⚠️  Pre-release checklist:"
echo "  [ ] Version updated in all files"
echo "  [ ] CHANGELOG.md updated"
echo "  [ ] README.md updated"
echo "  [ ] Tests passing"
echo "  [ ] Documentation complete"
echo ""
read -p "Ready to proceed? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo "❌ Release cancelled"
    exit 0
fi

# PyPI Release
if [ "$choice" = "1" ] || [ "$choice" = "4" ] || [ "$choice" = "5" ]; then
    echo ""
    echo "🐍 Building Python package..."
    
    # Clean previous builds
    rm -rf build/ dist/ *.egg-info/
    
    # Install build tools
    pip install build twine wheel --upgrade
    
    # Build
    python -m build
    
    echo "✅ Python package built"
    
    if [ "$choice" != "5" ]; then
        echo ""
        echo "📤 Uploading to PyPI..."
        python -m twine upload dist/*
        echo "✅ Published to PyPI: https://pypi.org/project/nife-mcp-server/$VERSION/"
    fi
fi

# NPM Release
if [ "$choice" = "2" ] || [ "$choice" = "4" ] || [ "$choice" = "5" ]; then
    echo ""
    echo "📦 Preparing NPM package..."
    
    # Make bin executable
    chmod +x bin/nife-mcp-server.js
    
    if [ "$choice" != "5" ]; then
        echo ""
        echo "📤 Publishing to NPM..."
        npm publish --access public
        echo "✅ Published to NPM: https://www.npmjs.com/package/@nife/mcp-server"
    else
        echo "✅ NPM package ready (not published)"
    fi
fi

# GitHub Release
if [ "$choice" = "3" ] || [ "$choice" = "4" ]; then
    echo ""
    echo "🐙 Creating GitHub release..."
    
    # Check if gh CLI is installed
    if ! command -v gh &> /dev/null; then
        echo "⚠️  GitHub CLI (gh) not installed"
        echo "   Install: https://cli.github.com/"
        echo "   Or create release manually at: https://github.com/nife-io/nife-mcp-server/releases/new"
    else
        # Create tag
        git tag -a "v$VERSION" -m "Release v$VERSION"
        git push origin "v$VERSION"
        
        # Create release
        gh release create "v$VERSION" \
            --title "Nife MCP Server v$VERSION" \
            --notes-file CHANGELOG.md \
            dist/*
        
        echo "✅ GitHub release created: https://github.com/nife-io/nife-mcp-server/releases/tag/v$VERSION"
    fi
fi

echo ""
echo "🎉 Release process complete!"
echo ""
echo "📋 Next steps:"
echo "  1. Announce release on social media"
echo "  2. Update documentation site"
echo "  3. Notify users via email/slack"
echo "  4. Update examples and tutorials"
echo ""
echo "📦 Package locations:"
if [ "$choice" = "1" ] || [ "$choice" = "4" ]; then
    echo "  PyPI: https://pypi.org/project/nife-mcp-server/$VERSION/"
fi
if [ "$choice" = "2" ] || [ "$choice" = "4" ]; then
    echo "  NPM: https://www.npmjs.com/package/@nife/mcp-server"
fi
if [ "$choice" = "3" ] || [ "$choice" = "4" ]; then
    echo "  GitHub: https://github.com/nife-io/nife-mcp-server/releases/tag/v$VERSION"
fi
echo ""
echo "✨ Happy releasing! ✨"
