FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0

COPY src ./src

EXPOSE 8000

# Multi-user HTTP MCP server. Each request carries its own user token in the
# Authorization header, so NO shared NIFE_ACCESS_TOKEN is needed.
# One worker + threads so the loaded schema is shared by all users.
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "1", "--threads", "16", "--timeout", "120", "nife_mcp_server.http_server:app"]
