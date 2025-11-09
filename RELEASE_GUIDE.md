# Release Guide for Nife MCP Server

## 📦 Release Options

### Option 1: NPM Package (Recommended for MCP Servers)
Most MCP servers are distributed via NPM for easy installation.

### Option 2: PyPI Package (Python Package Index)
Since this is a Python project, PyPI is a natural choice.

### Option 3: GitHub Release
Simple distribution via GitHub releases with binaries.

### Option 4: Docker Container
Containerized distribution for easy deployment.

---

## 🎯 Option 1: Release as NPM Package (Recommended)

### Why NPM?
- Claude Desktop config supports NPM packages natively
- Easy installation: `npx nife-mcp-server`
- Compatible with MCP ecosystem standards

### Step 1: Create package.json

```json
{
  "name": "@nife/mcp-server",
  "version": "1.0.0",
  "description": "Model Context Protocol server for Nife.io GraphQL API",
  "main": "src/nife_mcp_server/intelligent_main.py",
  "bin": {
    "nife-mcp-server": "./bin/nife-mcp-server.js"
  },
  "scripts": {
    "start": "python -m nife_mcp_server.intelligent_main"
  },
  "keywords": [
    "mcp",
    "model-context-protocol",
    "nife",
    "graphql",
    "claude",
    "ai"
  ],
  "author": "Your Name",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "https://github.com/yourusername/nife-mcp-server"
  },
  "engines": {
    "node": ">=16.0.0",
    "python": ">=3.8"
  },
  "dependencies": {
    "python-shell": "^5.0.0"
  }
}
```

### Step 2: Create bin/nife-mcp-server.js

```javascript
#!/usr/bin/env node

const { PythonShell } = require('python-shell');
const path = require('path');

const options = {
  mode: 'text',
  pythonPath: 'python3',
  pythonOptions: ['-u'],
  scriptPath: path.join(__dirname, '..'),
  args: ['-m', 'nife_mcp_server.intelligent_main']
};

PythonShell.run('', options, (err, results) => {
  if (err) throw err;
  console.log(results);
});
```

### Step 3: Publish to NPM

```bash
npm login
npm publish --access public
```

### Usage After Publishing

Users can install with:
```bash
npm install -g @nife/mcp-server
```

Claude Desktop config:
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

## 🐍 Option 2: Release as PyPI Package

### Step 1: Create setup.py

```python
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="nife-mcp-server",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Model Context Protocol server for Nife.io GraphQL API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/nife-mcp-server",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "flask>=2.0.0",
        "flask-cors>=3.0.0",
        "requests>=2.25.0",
    ],
    entry_points={
        "console_scripts": [
            "nife-mcp-server=nife_mcp_server.intelligent_main:main",
        ],
    },
)
```

### Step 2: Create pyproject.toml

```toml
[build-system]
requires = ["setuptools>=45", "wheel", "setuptools_scm[toml]>=6.2"]
build-backend = "setuptools.build_meta"

[project]
name = "nife-mcp-server"
version = "1.0.0"
description = "Model Context Protocol server for Nife.io GraphQL API"
readme = "README.md"
requires-python = ">=3.8"
license = {text = "MIT"}
keywords = ["mcp", "model-context-protocol", "nife", "graphql", "ai"]
authors = [
  {name = "Your Name", email = "your.email@example.com"}
]
classifiers = [
  "Development Status :: 4 - Beta",
  "Programming Language :: Python"
]
dependencies = [
  "flask>=2.0.0",
  "flask-cors>=3.0.0",
  "requests>=2.25.0",
]

[project.urls]
Homepage = "https://github.com/yourusername/nife-mcp-server"
Documentation = "https://github.com/yourusername/nife-mcp-server#readme"
Repository = "https://github.com/yourusername/nife-mcp-server"
```

### Step 3: Build and Publish

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Upload to PyPI
python -m twine upload dist/*
```

### Usage After Publishing

Users can install with:
```bash
pip install nife-mcp-server
```

Claude Desktop config:
```json
{
  "mcpServers": {
    "nife": {
      "command": "nife-mcp-server",
      "env": {
        "NIFE_ACCESS_TOKEN": "your_token"
      }
    }
  }
}
```

---

## 🐙 Option 3: GitHub Release

### Step 1: Prepare Repository

```bash
# Create .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
.env
.venv
*.egg-info/
dist/
build/
.DS_Store
EOF

# Initialize git (if not already)
git init
git add .
git commit -m "Initial commit"

# Create GitHub repository and push
git remote add origin https://github.com/yourusername/nife-mcp-server.git
git branch -M main
git push -u origin main
```

### Step 2: Create Release

1. Go to GitHub repository
2. Click "Releases" → "Create a new release"
3. Tag version: `v1.0.0`
4. Release title: `Nife MCP Server v1.0.0`
5. Description: List features and changes
6. Publish release

### Usage After Release

Users can install with:
```bash
git clone https://github.com/yourusername/nife-mcp-server.git
cd nife-mcp-server
pip install -r requirements.txt
```

Claude Desktop config:
```json
{
  "mcpServers": {
    "nife": {
      "command": "python",
      "args": ["-m", "nife_mcp_server.intelligent_main"],
      "cwd": "/path/to/nife-mcp-server",
      "env": {
        "NIFE_ACCESS_TOKEN": "your_token"
      }
    }
  }
}
```

---

## 🐳 Option 4: Docker Release

### Step 1: Create Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "nife_mcp_server.intelligent_main"]
```

### Step 2: Create docker-compose.yml

```yaml
version: '3.8'

services:
  nife-mcp-server:
    build: .
    environment:
      - NIFE_ACCESS_TOKEN=${NIFE_ACCESS_TOKEN}
    stdin_open: true
    tty: true
```

### Step 3: Build and Push

```bash
# Build
docker build -t yourusername/nife-mcp-server:1.0.0 .

# Tag as latest
docker tag yourusername/nife-mcp-server:1.0.0 yourusername/nife-mcp-server:latest

# Push to Docker Hub
docker login
docker push yourusername/nife-mcp-server:1.0.0
docker push yourusername/nife-mcp-server:latest
```

### Usage After Publishing

```bash
docker run -e NIFE_ACCESS_TOKEN=your_token yourusername/nife-mcp-server:latest
```

---

## 📋 Pre-Release Checklist

- [ ] Update version numbers in all files
- [ ] Update README.md with installation instructions
- [ ] Add LICENSE file (MIT recommended)
- [ ] Add CHANGELOG.md
- [ ] Test installation on fresh system
- [ ] Create comprehensive documentation
- [ ] Add example configurations
- [ ] Test with Claude Desktop
- [ ] Add CI/CD pipeline (GitHub Actions)
- [ ] Add badges to README (build status, version, etc.)

---

## 🎯 Recommended Approach

**For MCP Servers, I recommend a hybrid approach:**

1. **Primary**: Publish to NPM (easiest for Claude Desktop users)
2. **Secondary**: Publish to PyPI (for Python developers)
3. **Tertiary**: GitHub releases (for advanced users)
4. **Optional**: Docker Hub (for containerized deployments)

This gives users maximum flexibility in how they install and use your MCP server.

---

## 📚 Additional Files Needed

Create these files before release:

1. **LICENSE** - MIT recommended
2. **CHANGELOG.md** - Version history
3. **CONTRIBUTING.md** - Contribution guidelines
4. **CODE_OF_CONDUCT.md** - Community guidelines
5. **.github/workflows/publish.yml** - Auto-publish CI/CD

---

## 🚀 Next Steps

1. Choose your primary distribution method
2. Update version numbers and metadata
3. Test thoroughly
4. Create documentation
5. Publish!
6. Announce on:
   - MCP community forums
   - Nife.io community
   - Social media
   - Dev.to / Hashnode

Good luck with your release! 🎉
