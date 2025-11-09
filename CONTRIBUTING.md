# Contributing to Nife MCP Server

First off, thank you for considering contributing to Nife MCP Server! 🎉

Following these guidelines helps to communicate that you respect the time of the developers managing and developing this open source project. In return, they should reciprocate that respect in addressing your issue, assessing changes, and helping you finalize your pull requests.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [What We're Looking For](#what-were-looking-for)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Style Guidelines](#style-guidelines)
- [Community](#community)

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to support@nife.io.

## What We're Looking For

We love contributions! Here are some ways you can help:

### 🐛 Bug Reports
- Use the bug report template
- Include clear reproduction steps
- Provide relevant system information
- Share error logs if applicable

### 💡 Feature Requests
- Use the feature request template
- Explain the use case clearly
- Describe the expected behavior
- Consider implementation complexity

### 📝 Documentation
- Fix typos or unclear sections
- Add examples and tutorials
- Improve API documentation
- Translate documentation

### 💻 Code Contributions
- Bug fixes
- New features
- Performance improvements
- Test coverage
- Code refactoring

## How to Contribute

### Reporting Bugs

1. **Check existing issues** - Your bug might already be reported
2. **Use the bug report template** - It helps us help you faster
3. **Be specific** - Include versions, OS, error messages
4. **One bug per issue** - Makes tracking easier

### Suggesting Features

1. **Check existing issues** - Your idea might already exist
2. **Use the feature request template** - Helps us understand your needs
3. **Explain the problem** - Why do you need this feature?
4. **Describe the solution** - What would you like to see?

### Contributing Code

1. **Fork the repository**
   ```bash
   git clone https://github.com/your-username/nife-mcp-server.git
   cd nife-mcp-server
   ```

2. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

3. **Make your changes**
   - Write clear, commented code
   - Follow the style guide
   - Add tests if applicable
   - Update documentation

4. **Test your changes**
   ```bash
   # Install in development mode
   pip install -e .
   
   # Run the server
   python -m nife_mcp_server.intelligent_main
   
   # Test with Claude Desktop
   # (Update config and restart Claude)
   ```

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   # or
   git commit -m "fix: resolve bug in X"
   ```

   Use conventional commits:
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation only
   - `style:` - Code style (formatting, etc.)
   - `refactor:` - Code refactoring
   - `test:` - Adding tests
   - `chore:` - Maintenance tasks

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request**
   - Use a clear title and description
   - Reference any related issues
   - Explain what changed and why
   - Include screenshots if relevant

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Node.js 16+ (for NPM testing)
- Git
- Virtual environment tool

### Setup Steps

1. **Clone and navigate**
   ```bash
   git clone https://github.com/nife-io/nife-mcp-server.git
   cd nife-mcp-server
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -e .  # Install in editable mode
   ```

4. **Set up pre-commit hooks (optional)**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

5. **Run the server**
   ```bash
   python -m nife_mcp_server.intelligent_main
   ```

### Project Structure

```
nife-mcp-server/
├── src/
│   └── nife_mcp_server/
│       ├── __init__.py          # Package initialization
│       ├── __main__.py          # Entry point
│       ├── intelligent_main.py  # Main server logic
│       ├── schema_manager.py    # GraphQL schema handling
│       └── routes/
│           └── mcp.py           # MCP route handlers
├── tests/                       # Test files (to be added)
├── docs/                        # Documentation
└── bin/                         # Executable scripts
```

## Pull Request Process

### Before Submitting

- [ ] Code follows the style guide
- [ ] Comments are clear and helpful
- [ ] Documentation is updated
- [ ] Tests pass (if applicable)
- [ ] No merge conflicts
- [ ] Commit messages are clear

### Review Process

1. **Automated checks** - CI/CD will run automatically
2. **Code review** - Maintainers will review your code
3. **Discussion** - We may ask questions or suggest changes
4. **Approval** - Once approved, your PR will be merged
5. **Credit** - You'll be added to contributors!

### After Merging

- Your changes will be in the next release
- You'll be credited in CHANGELOG.md
- Consider joining the community!

## Style Guidelines

### Python Code

```python
# Use descriptive variable names
user_token = request.headers.get("Authorization")  # Good
t = request.headers.get("Authorization")  # Bad

# Add docstrings
def query_graphql(endpoint: str, query: str) -> dict:
    """
    Execute a GraphQL query against an endpoint.
    
    Args:
        endpoint: The GraphQL endpoint URL
        query: The GraphQL query string
    
    Returns:
        dict: The query response
    """
    pass

# Type hints where possible
def process_response(data: dict) -> Optional[str]:
    return data.get("result")

# Keep functions small and focused
# Maximum 50 lines per function
```

### Formatting

- **Line length**: 100 characters max
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Double quotes for strings
- **Imports**: Group and sort (stdlib, third-party, local)

### Documentation

```python
# Module docstring at top
"""
Module for handling GraphQL queries.

This module provides utilities for querying the Nife.io
GraphQL API and processing responses.
"""

# Class docstrings
class SchemaManager:
    """
    Manages GraphQL schema introspection and caching.
    
    Attributes:
        endpoint: The GraphQL endpoint URL
        token: Authentication token
    """

# Function docstrings
def introspect_schema(endpoint: str) -> dict:
    """
    Introspect a GraphQL schema.
    
    Args:
        endpoint: The GraphQL endpoint to introspect
    
    Returns:
        dict: The schema introspection result
    
    Raises:
        ConnectionError: If the endpoint is unreachable
    """
```

### Commit Messages

Follow conventional commits:

```bash
# Format
<type>(<scope>): <subject>

<body>

<footer>

# Examples
feat(schema): add caching for schema introspection

Implements LRU cache for schema introspection to improve
performance when making repeated queries.

Closes #123

fix(auth): handle expired tokens gracefully

Previously, expired tokens caused server crashes. Now they
return proper 401 errors with helpful messages.

Fixes #456
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

## Testing

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest

# Run with coverage
pytest --cov=nife_mcp_server

# Run specific test
pytest tests/test_schema.py
```

### Writing Tests

```python
import pytest
from nife_mcp_server import schema_manager

def test_schema_introspection():
    """Test basic schema introspection."""
    manager = schema_manager.SchemaManager("https://api.nife.io/graphql")
    schema = manager.introspect()
    assert schema is not None
    assert "types" in schema

def test_invalid_endpoint():
    """Test handling of invalid endpoints."""
    manager = schema_manager.SchemaManager("invalid-url")
    with pytest.raises(ValueError):
        manager.introspect()
```

## Documentation

### Updating Documentation

- Update README.md for user-facing changes
- Update inline code comments
- Add examples to QUICKSTART.md
- Update API docs in ENDPOINT_GUIDE.md

### Writing Good Documentation

```markdown
# Use clear headings

## Installation

Explain what the user needs to do:

1. Step one with command
   ```bash
   pip install nife-mcp-server
   ```

2. Step two with example
   ```python
   from nife_mcp_server import main
   ```

3. Expected result
   "You should see..."
```

## Community

### Getting Help

- **GitHub Issues**: For bugs and features
- **Discussions**: For questions and ideas
- **Email**: support@nife.io for private matters

### Communication Guidelines

- Be respectful and constructive
- Provide context and details
- Stay on topic
- Be patient with responses
- Help others when you can

### Recognition

Contributors are recognized in:
- README.md contributors section
- CHANGELOG.md for their contributions
- Release notes

## Questions?

Don't hesitate to ask! We're here to help:

- Open a question issue
- Email support@nife.io
- Check existing documentation

## Thank You!

Your contributions make Nife MCP Server better for everyone. We appreciate your time and effort! 🙏

---

**Happy Contributing!** 🚀

*Last updated: November 9, 2025*
