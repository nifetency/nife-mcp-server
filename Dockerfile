FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install the package with the hosted-server extra
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[http]"

# Run as an unprivileged user
RUN useradd --create-home --uid 10001 nife
USER nife

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=3)"

# No credentials are baked into the image. Configuration comes from env vars:
#   NIFE_GRAPHQL_URL, NIFE_EXPRESS_URL, NIFE_SITE_DOMAIN,
#   NIFE_ENV_ENCRYPTION_KEY (optional), NIFE_MCP_RATE_LIMIT_PER_MIN, NIFE_MCP_ALLOWED_ORIGINS
CMD ["nife-mcp-http"]
