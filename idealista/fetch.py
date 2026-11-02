"""idealista transport: plain curl_cffi with browser-impersonated TLS. No
browser, no login, no cookies kept across sessions. Egress: one sticky exit
per thread session (config.idealista_proxy(), knob IDEALISTA_EXIT); a
retryable failure drops the session, so the retry rides a fresh exit.

DataDome fronts www.idealista.com and www.idealista.it (research
2026-10-30, curl_cffi chrome / safari17_0 / edge101 on residential and
datacenter proxy exits):

  * The Spanish and Catalan renderings of www.idealista.com (/venta-viviendas/…,
    /inmueble/<id>/, /es/…, /ca/…) answer the 773-byte captcha-delivery
    page to every curl identity on every exit. The same pages under any
    other locale prefix (/en/, /fr/, /de/, /it/, /pt/, /nl/, /ru/) pass, so
    every request here carries a non-Spanish locale (refs.LANGUAGES).
  * The Accept-Language must be the exit's own (a Spanish exit announces
    Spanish): with an English list or no header even /en/ pages are 403.
    egress.accept_language(proxy) gives exactly that.
  * One Spanish residential exit served 12 list pages + a detail + an
    agency page + typeaheads back to back; an occasional single 403 on one
    URL clears on a fresh exit (the retry ladder). Every route under /ajax/
    (contact phones, totals, agency branding) is walled; the two JSON
    routes this module uses (locationsSuggest, listingOnDemandMultimedias)
    are not.
  * idealista.it passes on the same exits, its own Italian default locale
    included. idealista.pt is a Cloudflare challenge on every profile and
    exit, so refs refuses .pt links.

Upstream surfaces:
  LIST      GET /{lang}/<segment>/<location>/[pagina-N.htm]?adfilter_…&ordenado-por=…
            30 cards per page, capped at 60 pages (page 61 serves page 1
            again — api.py stops at refs.MAX_PAGES). A search with no
            match answers HTTP 404 with a "There are no listings" page:
            an empty page here, never an error.
  AREA      GET /{lang}/areas/<segment>/[pagina-N]?shape=((polyline)) — a
            drawn polygon; idealista.it spells it /aree/ and answers 400 for
            a polygon outside Italy.
  DETAIL    GET /{lang}/inmueble/<id>/ (/immobile/ on .it) — a dead id is an
            HTTP 404 "We couldn't find what you're looking for" page.
  PHOTOS    GET /listingOnDemandMultimedias/<id> — JSON, every photo / plan
            / video of a listing.
  AGENCY    GET /{lang}/pro/<slug>/[<segment>/[<location>/][pagina-N.htm]]
            — the microsite with its listing; unknown slug is HTTP 404.
  DIRECTORY GET /{lang}/agencias-inmobiliarias/<location>/inmobiliarias —
            the 15 featured agencies of a location (no paging).
  SUGGEST   GET /{lang}/locationsSuggest/<sale|rent>/<typology>/<Text> —
            the site's own location typeahead (JSON list).

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  IdealistaUpstreamError  transport failure / 5xx            — retryable
  IdealistaBlocked        DataDome 403 / 429 / challenge      — retryable
  IdealistaBadRequest     upstream 400                        — never retried
  IdealistaNotFound       dead listing / agency / page        — never retried
"""
import json
import os
import re
import sys
import threading
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from idealista import refs

IMPERSONATE = "chrome"
PAGE_TIMEOUT = 35       # list / agency pages are 300-470 KB
JSON_TIMEOUT = 20

PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "upgrade-insecure-requests": "1",
}
# The two JSON routes are fetched with the page's accept header alone:
# DataDome answers the XHR header set (accept: application/json +
# x-requested-with) with its 403 interstitial on every exit, warm or cold,
# and so does a navigation header set that carries BOTH
# upgrade-insecure-requests and a referer; the bare accept header is 200
# (header matrix on 2 fresh exits, 2026-11-01).
JSON_HEADERS = {"accept": PAGE_HEADERS["accept"]}

_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
_DATADOME_MARKERS = ("captcha-delivery.com", "geo.captcha-delivery", "Please enable JS and disable any ad blocker")
_ZERO_RESULTS_MARKER = 'id="zero-results-container"'


class IdealistaUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class IdealistaBlocked(IdealistaUpstreamError, Blocked):
    """DataDome / 403 / 429 / challenge page — retryable on a fresh exit."""


class IdealistaBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class IdealistaNotFound(NotFound):
    """Listing / agency / directory page does not exist — never retried."""


# ---- sessions ------------------------------------------------------------------

_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.idealista_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers["accept-language"] = egress.accept_language(proxy)
        _local.session = sess
    return sess


def _drop_session():
    """Close the thread's session: a refused exit must not be reused."""
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    """Run fn() under the shared retry policy (IdealistaUpstreamError only;
    NotFound / BadRequest surface immediately). Each retry drops the
    session, so it leaves through a fresh sticky exit."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except IdealistaUpstreamError as e:
            last = e
            _drop_session()
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


# ---- classification ------------------------------------------------------------

def page_title(text):
    match = _TITLE_RE.search(text or "")
    return match.group(1).strip() if match else ""


def is_datadome(text):
    head = (text or "")[:3000]
    return any(marker in head for marker in _DATADOME_MARKERS)


def is_zero_results(text):
    return _ZERO_RESULTS_MARKER in (text or "")


def _classify(resp, label, not_found_ok=False):
    """Map an HTTP response to the taxonomy; return the body text. A 404 is
    returned (not raised) when `not_found_ok` — list pages answer 404 for
    an empty search and past-the-end pages."""
    text = resp.text
    status = resp.status_code
    if status in (401, 403, 429) or is_datadome(text):
        raise IdealistaBlocked(f"HTTP {status} (anti-bot) for {label}")
    if status == 404:
        if not_found_ok:
            return text
        raise IdealistaNotFound(f"{label} not found")
    if status == 400:
        raise IdealistaBadRequest(f"idealista rejected the request for {label}")
    if status != 200:
        raise IdealistaUpstreamError(f"HTTP {status} for {label}")
    return text


def _url(country, path, query=None):
    url = refs.absolute(country, path)
    if query:
        url += "?" + urlencode(query, doseq=True)
    return url


def _get_html(country, path, query, label, not_found_ok=False):
    def once():
        try:
            resp = _session().get(_url(country, path, query), headers=PAGE_HEADERS,
                                  timeout=PAGE_TIMEOUT)
        except Exception as e:
            raise IdealistaUpstreamError(f"request failed: {type(e).__name__}: {e}")
        text = _classify(resp, label, not_found_ok=not_found_ok)
        if "<html" not in text[:2000].lower():
            raise IdealistaBlocked(f"non-HTML answer for {label}: {text[:80]!r}")
        return text, resp.status_code
    return _retrying(once)


def _get_json(country, path, label):
    def once():
        try:
            resp = _session().get(_url(country, path), headers=JSON_HEADERS, timeout=JSON_TIMEOUT)
        except Exception as e:
            raise IdealistaUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code == 400 and (resp.text or "").strip() in ("[]", ""):
            return []          # the typeahead's "nothing matched" answer
        text = _classify(resp, label)
        try:
            return json.loads(text)
        except ValueError:
            raise IdealistaBlocked(f"non-JSON answer for {label}: {text[:80]!r}")
    return _retrying(once)


# ---- surfaces ------------------------------------------------------------------

def fetch_listing_page(country, path, query=None):
    """One search / area / agency-listing page. Returns (html, status): a 404
    is a zero-result or past-the-end page (parsers decide), not an error."""
    return _get_html(country, path, query, f"listing {path}", not_found_ok=True)


def fetch_detail(country, language, property_id):
    """The listing page HTML; a dead id raises IdealistaNotFound."""
    path = refs.detail_path(country, language, property_id)
    html, _status = _get_html(country, path, None, f"listing {property_id}")
    return html


def fetch_multimedia(country, property_id):
    """The listing's photo / plan / video JSON (listingOnDemandMultimedias)."""
    payload = _get_json(country, refs.multimedia_path(property_id), f"photos of {property_id}")
    return payload if isinstance(payload, dict) else {}


def fetch_agency(country, language, slug, segment=None, location=None, page=1):
    """The agency microsite (its default listing) or one of its listing
    pages. An unknown slug raises IdealistaNotFound (the site's error page);
    an empty or past-the-end listing page is a 404 that still carries the
    microsite and a #zero-results-container, returned as (html, 404)."""
    path = refs.agency_path(country, language, slug, segment, location, page)
    html, status = _get_html(country, path, None, f"agency {slug}", not_found_ok=True)
    if status == 404 and not (segment and is_zero_results(html)):
        raise IdealistaNotFound(f"agency {slug} not found")
    return html, status


def fetch_directory(country, language, location):
    """The featured-agencies page of a location (unknown location: NotFound)."""
    path = refs.directory_path(country, language, location)
    html, _status = _get_html(country, path, None, f"agencies in {location}")
    return html


def fetch_suggest(country, language, operation, typology, text):
    """The site's location typeahead -> list of suggestion dicts."""
    text = text.strip()
    text = text[:1].upper() + text[1:].lower()     # what the site's own JS sends
    payload = _get_json(country, refs.suggest_path(country, language, operation, typology, text),
                        f"locations matching {text!r}")
    return payload if isinstance(payload, list) else []
