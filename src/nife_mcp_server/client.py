#!/usr/bin/env python3
"""
Nife.io GraphQL HTTP client.

Separated from Flask routes so the MCP server can import it without
pulling in Flask as a dependency.
"""
import json
import logging
import time
import requests
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

NIFE_GRAPHQL_ENDPOINT = "https://api.nife.io/graphql"


class NifeGraphQLClient:
    """Thin HTTP client for the Nife.io GraphQL API."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.endpoint = NIFE_GRAPHQL_ENDPOINT

    def execute_query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Execute a GraphQL query against the Nife.io API.

        Always returns a dict. On transport/network errors the dict will
        contain an ``errors`` key so callers can use a single code path.
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "nife-mcp-server/1.0.0",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        start = time.time()
        try:
            logger.info(f"GraphQL → {query[:100].strip()}…")
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            elapsed = time.time() - start
            logger.info(f"GraphQL ← {response.status_code} in {elapsed:.2f}s")

            response.raise_for_status()
            result = response.json()

            if "errors" in result:
                logger.error(f"GraphQL errors: {result['errors']}")

            return result

        except requests.exceptions.Timeout:
            logger.error(f"GraphQL timeout after {timeout}s")
            return {"errors": [{"message": f"Request timeout after {timeout} seconds"}]}

        except requests.exceptions.ConnectionError:
            logger.error("Connection error to Nife.io API")
            return {"errors": [{"message": "Connection error to Nife.io API"}]}

        except requests.exceptions.HTTPError as exc:
            logger.error(f"HTTP error: {exc}")
            return {"errors": [{"message": f"HTTP error: {exc}"}]}

        except requests.exceptions.RequestException as exc:
            logger.error(f"Request failed: {exc}")
            return {"errors": [{"message": f"Request failed: {exc}"}]}

        except json.JSONDecodeError:
            # Must come before ValueError since JSONDecodeError is a subclass of it
            logger.error("Invalid JSON response from API")
            return {"errors": [{"message": "Invalid JSON response from API"}]}

        except (ValueError, TypeError) as exc:
            # Catches invalid timeout values and other parameter errors
            logger.error(f"Invalid request parameter: {exc}")
            return {"errors": [{"message": f"Invalid request parameter: {exc}"}]}
