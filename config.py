"""Configuration for the Idealista Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT             port the API listens on (default 8000)
    IDEALISTA_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                     (default: none — direct). idealista.com and idealista.it sit
                     behind DataDome. A Spanish residential proxy is the
                     connection it trusts most: set one here for steady volume,
                     so every retry after a block leaves through a fresh IP.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

IDEALISTA_PROXY = os.environ.get("IDEALISTA_PROXY") or None


def idealista_proxy():
    """The proxy for one curl session (None = direct)."""
    return os.environ.get("IDEALISTA_PROXY") or None
