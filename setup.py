from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="nife-mcp-server",
    version="1.0.0",
    author="Nife Team",
    author_email="support@nife.io",
    description="Model Context Protocol server for Nife.io GraphQL API - Intelligent schema-driven implementation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nife-io/nife-mcp-server",
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
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Framework :: Flask",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
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
    project_urls={
        "Bug Reports": "https://github.com/nife-io/nife-mcp-server/issues",
        "Documentation": "https://github.com/nife-io/nife-mcp-server#readme",
        "Source": "https://github.com/nife-io/nife-mcp-server",
    },
)
