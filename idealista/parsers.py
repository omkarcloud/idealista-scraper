"""HTML / JSON -> clean dicts for every /idealista/* endpoint. Pure functions,
no I/O.

The pages are server-rendered (no JSON-LD, no hydration blob): listing
cards are `<article class="item" data-element-id=…>`, the detail page keeps
its facts in feature lists plus three inline JS objects (`var config`,
`var adDetail`, `var adMultimediasInfo` — a JS literal with unquoted keys,
read with a tolerant converter), the coordinates only inside the Google
static-map image URL, and the agency microsite in `#office-info` /
`#office-contact` plus the same listing cards.

Everything is rendered in the locale of the request (English by default;
Spanish is DataDome-walled, fetch.py), so the parsed numbers go through
locale-agnostic helpers (thousands separators of any kind are dropped, a
decimal comma is accepted) and the raw feature lines are kept verbatim next
to the fields parsed out of them, so a reader in any locale loses nothing.

Value conventions (shared with the other scraper packages):
  * prices   {"amount": 2495000, "currency": "EUR", "period": null | "month",
              "text": "2,495,000 €"}; null when the site shows "price on request"
  * dates    ISO "2026-10-30" (the site prints "Listing updated on 30 October";
             the year is inferred from `today`, never in the future)
  * keys     snake_case; `link` not `url`; booleans as questions; absent -> null

Fixtures captured 2026-10-30 (idealista/fixtures/): Madrid sale / rent /
rooms / new-development / offices list pages, a drawn-area page, a
zero-result page (HTTP 404 with a zero-results container), the page-61
cap, a Milan (.it) list page; a private rental, a professional sale, a
new-development unit, a room, an office and a Milan listing detail, a dead
listing; the Engel & Völkers Barcelona and Clikalia microsites with a
listing page, a dead microsite, a past-the-end agency listing page; the
Alicante and Milan agencies directories and both indexes; three typeahead
answers and one listingOnDemandMultimedias JSON; a DataDome block page.
"""
import html as html_module
import json
import re
from datetime import date

from bs4 import BeautifulSoup

from idealista import refs

_MONTHS = {
    # en / es / it / fr / de / pt / nl month names and stems -> number
    "jan": 1, "ene": 1, "gen": 1, "feb": 2, "fev": 2, "fév": 2, "mar": 3, "mär": 3, "apr": 4, "abr": 4, "avr": 4,
    "may": 5, "mag": 5, "mai": 5, "mei": 5, "jun": 6, "giu": 6, "jui": 6, "juil": 7, "jul": 7, "lug": 7, "aug": 8, "ago": 8,
    "aoû": 8, "sep": 9, "set": 9, "oct": 10, "ott": 10, "okt": 10, "nov": 11, "dec": 12, "dic": 12, "déc": 12, "dez": 12,
}
_WS_RE = re.compile(r"\s+")
_INT_RE = re.compile(r"\d[\d.,   ]*")
_DECIMAL_RE = re.compile(r"\d+(?:[.,]\d+)?")
_SIZE_RE = re.compile(r"(\d[\d.,   ]*)\s*m²")
_ROOMS_RE = re.compile(r"(\d+)\s*(?:bed|hab|room|zimmer|chambre|pièce|quarto|kamer|комн|stanz|local|dorm)", re.I)
_BATHS_RE = re.compile(r"(\d+)\s*(?:bath|baño|bagn|salle|bad|casa de banho|badkamer|ванн)", re.I)
_PRICE_PER_M2_RE = re.compile(r"([\d.,   ]+)\s*€\s*/\s*m²")
_PERIOD_RE = re.compile(r"/\s*(month|mes|mese|mois|monat|mês|maand|мес|week|semana|settimana|semaine|woche|day|día|giorno|jour|tag)",
                        re.I)
_FLOOR_RE = re.compile(r"(?:floor|planta|piano|étage|stock|andar|verdieping|этаж|ground|bajo|basement|sótano|attic|ático)",
                       re.I)
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_ENERGY_CLASS_RE = re.compile(r"icon-energy-c-([a-g])\b")
_CONFIG_RE = re.compile(r"var config\s*=\s*\{(.*?)\n\s*\};", re.S)
_CONFIG_SCALAR_RE = re.compile(r"""^\s*([A-Za-z0-9_]+)\s*:\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|true|false|null)\s*,?\s*$""")
_STATICMAP_CENTER_RE = re.compile(r"staticmap\?[^\"']*?center=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)")
_LIST_TOTAL_RE = re.compile(r"(\d[\d.,   ]*)")
_AGO_RE = re.compile(r"^\s*(\d+)\s*(\w+)\s*$")
_PERCENT_RE = re.compile(r"(\d+)\s*%")
_DAY_MONTH_RE = re.compile(r"(\d{1,2})\.?\s+(?:de\s+|di\s+)?([^\s\d]{3,})", re.I)

MULTIMEDIA_BASE = "https://img4.idealista.com/blur/"


# ---- scalar helpers ------------------------------------------------------------------

def _soup(html):
    return BeautifulSoup(html or "", "lxml")


def _text(node, sep=" "):
    return _WS_RE.sub(" ", node.get_text(sep, strip=True)).strip() if node is not None else ""


def _clean(value):
    if value is None:
        return None
    value = _WS_RE.sub(" ", str(value)).strip()
    return value or None


def parse_int(value):
    """'2,495,000' / '2.495.000' / '1 114' -> 2495000; no digits -> None."""
    if value is None:
        return None
    match = _INT_RE.search(str(value))
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    return int(digits) if digits else None


def parse_decimal(value):
    """'153,1' / '153.1' / '26' -> float; None when no number."""
    if value is None:
        return None
    match = _DECIMAL_RE.search(str(value).replace(" ", "").replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def parse_price(text):
    """'2,495,000 €' / '1,114 €/month' / '620€/mese' -> price dict; None for
    masked / absent prices (the site prints 'Price on request')."""
    text = _clean(text)
    if not text:
        return None
    amount = parse_int(text)
    if amount is None:
        return None
    period = None
    match = _PERIOD_RE.search(text)
    if match:
        word = match.group(1).lower()
        period = ("month" if word[:2] in ("mo", "me", "mê", "ма", "ma") and word not in ("maand",) or word == "maand" or word.startswith("mo")
                  else "week" if word[:1] in ("w", "s") else "day")
        if word in ("month", "mes", "mese", "mois", "monat", "mês", "maand", "мес"):
            period = "month"
        elif word in ("week", "semana", "settimana", "semaine", "woche"):
            period = "week"
        else:
            period = "day"
    return {"amount": amount, "currency": "EUR", "period": period, "text": text}


def parse_update_date(text, today=None):
    """'Listing updated on 30 October' -> '2026-10-30' (the year is the
    latest one that keeps the date in the past)."""
    text = _clean(text)
    if not text:
        return None
    match = _DAY_MONTH_RE.search(text)
    if not match:
        return None
    day = int(match.group(1))
    word = match.group(2).lower()
    month = _MONTHS.get(word[:4]) or _MONTHS.get(word[:3])   # juillet (4) before juin (3)
    if not month or not 1 <= day <= 31:
        return None
    today = today or date.today()
    year = today.year
    try:
        when = date(year, month, day)
    except ValueError:
        return None
    if when > today:
        try:
            when = date(year - 1, month, day)
        except ValueError:
            return None
    return when.isoformat()


def _absolute(country, href):
    if not href:
        return None
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http"):
        return href
    return refs.absolute(country, href if href.startswith("/") else "/" + href)


def _strip_locale(href):
    """'/en/inmueble/1/' -> '/inmueble/1/' (links stay locale-free); an
    absolute idealista link keeps its host."""
    href = href or ""
    if href.startswith("http"):
        match = re.match(r"^(https?://[^/]+)(/.*)?$", href)
        if match:
            return match.group(1) + (refs._LANG_PREFIX_RE.sub("", match.group(2) or "/") or "/")
        return href
    return refs._LANG_PREFIX_RE.sub("", href) or "/"


# Detail pages name some typologies more finely than the search verticals
# do (a villa is typology 'chalet', not 'home'): every such name maps onto
# its public property_type; the site's raw value stays in `typology`.
_TYPOLOGY_ALIASES = {
    "chalet": "homes", "flat": "homes", "countryhouse": "homes", "country_house": "homes",
    "duplex": "homes", "penthouse": "homes", "studio": "homes", "apartment": "homes",
    "loft": "homes", "villa": "homes", "house": "homes", "atticstudio": "homes",
    "bedroom": "rooms", "premise": "premises", "premises": "premises", "commercial": "premises",
    "local": "premises", "parking": "garages", "plot": "lands", "storage": "storage_rooms",
    "promotion": "new_developments",
}


def _public_type(typology):
    """The site's typology key -> the public property_type (None when the
    site uses a name we have not seen; the raw value stays in `typology`)."""
    for public, key in refs.PROPERTY_TYPES.items():
        if key == typology:
            return public
    return _TYPOLOGY_ALIASES.get((typology or "").lower())


# ---- the inline JS objects -------------------------------------------------------------

def parse_config(html):
    """The scalar keys of the page's `var config = {...}` block."""
    match = _CONFIG_RE.search(html or "")
    if not match:
        return {}
    out = {}
    for line in match.group(1).splitlines():
        found = _CONFIG_SCALAR_RE.match(line)
        if not found:
            continue
        key, raw = found.group(1), found.group(2)
        if raw.startswith(("'", '"')):
            value = raw[1:-1].replace("\\'", "'").replace('\\"', '"').replace("\\/", "/")
        elif raw == "true":
            value = True
        elif raw == "false":
            value = False
        elif raw == "null":
            value = None
        else:
            value = float(raw) if "." in raw else int(raw)
        out[key] = value
    return out


def _js_object_to_json(text):
    """A JS literal with unquoted keys ({isPlan:false,hoverText:"x"}) ->
    parsed JSON; None when it cannot be read."""
    quoted = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)
    try:
        return json.loads(quoted)
    except ValueError:
        return None


def _js_array(html, name):
    """The `name: [...]` array of adMultimediasInfo as parsed JSON (or [])."""
    match = re.search(rf"\b{name}\s*:\s*(\[)", html or "")
    if not match:
        return []
    start = match.start(1)
    depth, in_string, escape, quote = 0, False, False, ""
    for index in range(start, len(html)):
        char = html[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                in_string = False
            continue
        if char in "\"'":
            in_string, quote = True, char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                parsed = _js_object_to_json(html[start:index + 1])
                return parsed if isinstance(parsed, list) else []
    return []


# ---- listing cards ------------------------------------------------------------------

def _card_detail_spans(card):
    return [_text(span) for span in card.select(".item-detail-char .item-detail")]


def _parse_floor(text):
    """'2nd floor exterior with lift' -> {"text", "is_exterior", "has_lift"}."""
    text = _clean(text)
    if not text:
        return None
    low = text.lower()
    exterior = True if re.search(r"\bexterior|außen|extérieur|esterno|buiten", low) else \
        False if re.search(r"\binterior|innen|intérieur|interno|binnen", low) else None
    lift = True if re.search(r"with lift|con ascensor|con ascensore|avec ascenseur|mit aufzug|com elevador|met lift|с лифтом", low) else \
        False if re.search(r"without lift|sin ascensor|senza ascensore|sans ascenseur|ohne aufzug|sem elevador|zonder lift|без лифта", low) else None
    return {"text": text, "is_exterior": exterior, "has_lift": lift}


def parse_card(card, country, operation=None, property_type=None):
    """One `<article class="item">` -> a result record."""
    ad_id = _clean(card.get("data-element-id"))
    link = card.select_one("a.item-link")
    title = _clean(link.get("title") or _text(link)) if link else None
    href = _strip_locale(link.get("href")) if link else None
    price_node = card.select_one(".item-price")
    price = parse_price(_text(price_node)) if price_node else None
    per_m2 = parse_int(_text(card.select_one(".item-price-by-area")))
    spans = _card_detail_spans(card)
    rooms = size = floor = None
    parking = None
    extras = []
    for span in spans:
        low = span.lower()
        size_match = _SIZE_RE.search(span)
        rooms_match = _ROOMS_RE.search(span)
        if _PRICE_PER_M2_RE.search(span):          # offices / premises print it among the details
            per_m2 = per_m2 or parse_int(_PRICE_PER_M2_RE.search(span).group(1))
        elif size_match and size is None and "room size" not in low:
            size = parse_int(size_match.group(1))
        elif rooms_match and rooms is None and "m²" not in span:
            rooms = int(rooms_match.group(1))
        elif _FLOOR_RE.search(low) and floor is None and "m²" not in span:
            floor = _parse_floor(span)
        elif re.search(r"parking|garage|garaje|plaza", low) and "m²" not in span:
            parking = "optional" if re.search(r"optional|opcional|opzionale|optionnel|facoltativ", low) else "included"
            extras.append(span)
        else:
            extras.append(span)
    description = card.select_one(".item-description")
    tags = [_text(t) for t in card.select(".listing-tags")]
    ribbons = [_text(r) for r in card.select(".item-ribbon") if _text(r)]
    counter = card.select_one(".item-multimedia-pictures__counter")
    photos_count = None
    if counter:
        numbers = re.findall(r"\d+", _text(counter))
        photos_count = int(numbers[-1]) if numbers else None
    thumb = card.select_one(".item-gallery img, picture img")
    thumbnail = _clean(thumb.get("src") or thumb.get("data-ondemand-img")) if thumb else None
    buttons = {b.get("data-button-type") for b in card.select("[data-button-type]")}
    branding = card.select_one(".logo-branding a")
    agency = None
    if branding:
        slug_match = refs._LINK_AGENCY_RE.search(branding.get("href") or "")
        logo = branding.select_one("img")
        agency = {
            "name": _clean(branding.get("title") or (logo.get("alt") if logo else None)),
            "slug": slug_match.group(1) if slug_match else None,
            "link": refs.agency_link(country, slug_match.group(1)) if slug_match else None,
            "logo": _clean(logo.get("src")) if logo else None,
        }
    fresh = card.select_one(".item-detail.txt-highlight-red")
    listed_ago = _text(fresh) if fresh else None
    if listed_ago and listed_ago in extras:
        extras.remove(listed_ago)
    classes = " ".join(card.get("class") or [])
    return {
        "id": ad_id,
        "link": _absolute(country, href) if href else (refs.property_link(country, ad_id) if ad_id else None),
        "title": title,
        "operation": operation,
        "property_type": property_type,
        "price": price,
        "price_per_m2": per_m2,
        "rooms": rooms,
        "size_m2": size,
        "floor": floor,
        "parking": parking,
        "details": spans,
        "description": _text(description) or None,
        "tags": tags,
        "ribbons": ribbons,
        "listed_ago": listed_ago,
        "is_new_listing": bool(listed_ago),
        "photos_count": photos_count,
        "thumbnail": thumbnail,
        "has_floor_plan": "PLAN" in buttons,
        "has_video": "VIDEO" in buttons,
        "has_3d_tour": "VIRTUAL_TOUR_3D" in buttons,
        "has_virtual_tour": "VIRTUAL_TOUR" in buttons or "VIRTUAL_TOUR_360" in buttons,
        "has_home_staging": "HOME_STAGING" in buttons,
        "has_map": "MAP" in buttons,
        "is_professional": card.get("data-is-professional-ad") == "true",
        "is_highlighted": "item_hightop" in classes or "item_featured" in classes,
        "is_offmarket": card.get("data-is-offmarket") == "true",
        "has_online_booking": card.get("data-online-booking") == "true",
        "agency": agency,
    }


def parse_list_total(html_or_soup):
    """The result count in the page h1 ('Property for sale in Madrid, Spain:
    19,831 houses and flats'); None when absent (zero-result pages)."""
    soup = html_or_soup if isinstance(html_or_soup, BeautifulSoup) else _soup(html_or_soup)
    node = soup.select_one("#h1-container__text") or soup.select_one("h1")
    text = _text(node)
    if not text:
        return None
    # "Property for sale in Madrid, Spain: 19,831 houses and flats" / "17,375
    # flats for sale in Madrid" / "Property for sale, 28013, Madrid: 294
    # houses" — the count is the number right after the last colon when
    # there is one, else the first number of the sentence.
    if ":" in text:
        text = text.rsplit(":", 1)[1]
    match = _LIST_TOTAL_RE.search(text)
    return parse_int(match.group(1)) if match else None


def _canonical(soup):
    link = soup.select_one('link[rel="canonical"]')
    return _clean(link.get("href")) if link else None


def _current_page(soup):
    node = soup.select_one(".pagination li.selected")
    return parse_int(_text(node)) if node else None


def parse_listing(html, country, operation=None, property_type=None, page=1):
    """A search / area / agency listing page -> {"total", "results", "page",
    "has_next", "link", "title", "is_zero_results"}. A zero-result page (the
    site's HTTP 404 with #zero-results-container) parses to an empty page."""
    soup = _soup(html)
    zero = soup.select_one("#zero-results-container") is not None
    cards = [parse_card(card, country, operation, property_type)
             for card in soup.select("article.item[data-element-id]")]
    cards = [c for c in cards if c["id"]]
    total = None if zero else parse_list_total(soup)
    selected = _current_page(soup)
    has_next = soup.select_one(".pagination li.next a") is not None
    # Past the site's cap (60 pages) the server renders page 1 again: treat a
    # mismatch between the requested and rendered page as "past the end".
    if page and selected and selected != page:
        cards, has_next = [], False
    title = soup.select_one("title")
    return {
        "total": total,
        "results": cards,
        "page": selected or page,
        "has_next": has_next and bool(cards),
        "link": _canonical(soup),
        "title": _text(title).split("—")[0].strip() if title else None,
        "is_zero_results": zero,
    }


def is_not_found_page(html):
    """The site's generic 'We couldn't find what you're looking for' page
    (HTTP 404 for a dead listing / agency; no listing content)."""
    text = html or ""
    return ('class="not-found' in text or 'class="error-page' in text
            or "does not correspond to any page" in text
            or "We couldn’t find" in text or "We couldn't find" in text
            or 'id="main"' not in text and "<article" not in text) and 'data-element-id' not in text


# ---- listing detail -------------------------------------------------------------------

def _feature_sections(soup):
    """[{"title": "Basic features", "items": [...]}, ...] in page order."""
    sections = []
    for block in soup.select(".details-property_features"):
        heading = block.find_previous(["h2", "h3"])
        items = [_text(li) for li in block.select("li")]
        items = [i for i in items if i]
        if not items:
            continue
        sections.append({"title": _text(heading) or None, "items": items})
    return sections


def _all_feature_lines(sections):
    return [item for section in sections for item in section["items"]]


def _parse_energy(soup, lines):
    """{"rating", "consumption", "emissions"} from the certificate block."""
    rating = None
    consumption = emissions = None
    consumption_rating = emissions_rating = None
    for node in soup.select("[class*=icon-energy-c-]"):
        classes = " ".join(node.get("class") or [])
        match = _ENERGY_CLASS_RE.search(classes)
        letter = match.group(1).upper() if match else None
        text = _text(node)
        parent = _text(node.parent).lower() if node.parent else ""
        value = parse_decimal(text)
        if re.search(r"consum|verbrauch|consom", parent):
            consumption, consumption_rating = value, letter or consumption_rating
        elif re.search(r"emission|emisi|emiss", parent):
            emissions, emissions_rating = value, letter or emissions_rating
        if letter and rating is None:
            rating = letter
    exempt = any(re.search(r"\bexempt|exento|esente|exempté|befreit|isento|vrijgesteld", line, re.I) for line in lines)
    in_process = any(re.search(r"in process|en trámite|in corso|en cours|in bearbeitung", line, re.I) for line in lines)
    if rating is None and consumption is None and emissions is None and not exempt and not in_process:
        return None
    return {
        "rating": rating,
        "consumption_rating": consumption_rating or rating,
        "consumption_kwh_m2_year": consumption,
        "emissions_rating": emissions_rating or rating,
        "emissions_kg_co2_m2_year": emissions,
        "is_exempt": exempt,
        "is_in_process": in_process,
    }


def _parse_lines(lines):
    """The facts a feature line carries (English + Spanish/Italian/French/
    German/Portuguese stems), kept next to the raw lines."""
    out = {"size_m2": None, "usable_size_m2": None, "plot_size_m2": None, "rooms": None, "bathrooms": None,
           "year_built": None, "orientation": None, "heating": None, "condition": None, "floor": None,
           "has_lift": None, "is_exterior": None, "has_terrace": None, "has_balcony": None,
           "has_garden": None, "has_swimming_pool": None, "has_air_conditioning": None, "has_storage_room": None,
           "has_wardrobes": None, "parking": None, "is_furnished": None, "is_accessible": None,
           "is_new_development": False}
    for line in lines:
        low = line.lower()
        # One line can carry several areas ("1,478 m² built, 1,256 m² floor
        # area"): each number is labelled by the words right after it (and,
        # for the first, the words before it: "Land plot of 2,047 m²").
        size_matches = list(_SIZE_RE.finditer(line))
        for index, size_match in enumerate(size_matches):
            value = parse_int(size_match.group(1))
            end = size_matches[index + 1].start() if index + 1 < len(size_matches) else len(line)
            label = line[size_match.end():end].lower()
            if index == 0:
                label = line[:size_match.start()].lower() + " " + label
            if re.search(r"usable|floor area|útil|calpest|habitable|wohnfl|úteis|bruikbaar|surface habitable", label):
                out["usable_size_m2"] = out["usable_size_m2"] or value
            elif re.search(r"plot|parcela|terreno|terrain|grundst|lote|perceel|land", label) and "built" not in label:
                out["plot_size_m2"] = out["plot_size_m2"] or value
            elif re.search(r"room size|tamaño de la habitación", label):
                out.setdefault("room_size_m2", value)
            elif out["size_m2"] is None:
                out["size_m2"] = value
        if out["rooms"] is None:
            match = _ROOMS_RE.search(line)
            if match and "m²" not in line and not re.search(r"people|personas|persone|flatmate", low):
                out["rooms"] = int(match.group(1))
        if out["rooms"] is None and re.search(r"^no bedroom|^sin dormitorio|^nessuna camera|^studio", low):
            out["rooms"] = 0
        if out["bathrooms"] is None:
            match = _BATHS_RE.search(line)
            if match:
                out["bathrooms"] = int(match.group(1))
        if re.search(r"built in|construido en|costruito nel|construit en|baujahr|construído em|bouwjaar|построен", low):
            year = _YEAR_RE.search(line)
            out["year_built"] = int(year.group(1)) if year else out["year_built"]
        if re.search(r"^orientation|^orientación|^orientazione|^ausrichtung|^orientação|^oriëntatie", low):
            out["orientation"] = line.split(" ", 1)[1] if " " in line else line
        if re.search(r"heating|calefacción|riscaldamento|chauffage|heizung|aquecimento|verwarming", low) \
                and not re.search(r"air condition|aire acondicionado|aria condizionata|climatisation|klimaanlage", low):
            out["heating"] = line
        if re.search(r"second hand|good condition|segunda mano|buen estado|buono stato|bon état|gebraucht|guter zustand", low):
            out["condition"] = "good"
        elif re.search(r"needs renovat|to be restored|para reformar|da ristrutturare|à rénover|renovierungsbed|para renovar", low):
            out["condition"] = "needs_renovation"
        elif re.search(r"new housing development|new development|new build|brand new|obra nueva|nuova costruzione|neubau|construção nova", low):
            out["condition"] = out["condition"] or "new_build"
            out["is_new_development"] = True
        if _FLOOR_RE.search(low) and out["floor"] is None and "m²" not in line and not re.search(r"building of|edificio de|floors$|plantas$", low):
            floor = _parse_floor(line)
            out["floor"] = floor["text"]
            out["is_exterior"] = floor["is_exterior"] if floor["is_exterior"] is not None else out["is_exterior"]
            out["has_lift"] = floor["has_lift"] if floor["has_lift"] is not None else out["has_lift"]
        if re.search(r"with lift|con ascensor|con ascensore|avec ascenseur|mit aufzug|com elevador|met lift", low):
            out["has_lift"] = True
        elif re.search(r"no lift|without lift|sin ascensor|senza ascensore|sans ascenseur|ohne aufzug|sem elevador|zonder lift", low):
            out["has_lift"] = False
        if re.search(r"\bterrace|terraza|terrazz|terrasse|terraço|terras\b", low):
            out["has_terrace"] = True
        if re.search(r"balcon|balkon|balcão|varanda", low):
            out["has_balcony"] = True
        if re.search(r"garden|jardín|jardin|giardino|garten|jardim|tuin", low):
            out["has_garden"] = True
        if re.search(r"swimming pool|piscina|piscine|pool|schwimmbad|zwembad", low):
            out["has_swimming_pool"] = True
        if re.search(r"air condition|aire acondicionado|aria condizionata|climatisation|klimaanlage|ar condicionado|airco", low):
            out["has_air_conditioning"] = True
        if re.search(r"storage room|storeroom|trastero|ripostiglio|cantina|débarras|abstellraum|arrecadação|berging", low):
            out["has_storage_room"] = True
        if re.search(r"wardrobe|armario|armadi|placard|einbauschr|roupeiro|kasten", low):
            out["has_wardrobes"] = True
        if re.search(r"parking|garage|garaje|plaza de|posto auto|stationnement|stellplatz|estacionamento", low):
            if re.search(r"included|incluid|inclus|compres|inbegriffen|incluíd|inbegrepen", low):
                out["parking"] = "included"
            elif re.search(r"optional|opcional|opzional|optionnel|optionaal", low):
                out["parking"] = "optional"
            elif out["parking"] is None:
                out["parking"] = "yes"
        if re.match(r"^(?:(?:un|not )?furnished|(?:sin |no )?amueblad|(?:non )?arredat|(?:non )?meublé|(?:un)?möbliert|"
                    r"(?:não )?mobilad|(?:on)?gemeubileerd)", low):
            out["is_furnished"] = not re.match(r"^(?:unfurnished|not furnished|sin amueblar|no amueblad|non arredat|non meublé|"
                                               r"unmöbliert|não mobilad|ongemeubileerd)", low)
        if re.search(r"reduced mobility|accessible|movilidad reducida|accesib|accessib|mobilité réduite|barrierefrei", low):
            out["is_accessible"] = True
    return out


def _parse_location(soup, html):
    """#headerMap address lines + the static-map coordinates."""
    lines = [_text(li) for li in soup.select("#headerMap li")]
    lines = [l for l in lines if l]
    lat = lng = None
    match = _STATICMAP_CENTER_RE.search(html or "")
    if match:
        lat, lng = float(match.group(1)), float(match.group(2))
    address = None
    rest = list(lines)
    if lines and not re.match(r"^(subdistrict|district|barrio|distrito|quartiere|zona|quartier|bezirk|freguesia|wijk)\b", lines[0], re.I) \
            and len(lines) >= 3:
        address, rest = lines[0], lines[1:]
    area = district = city = region = None
    for line in rest:
        low = line.lower()
        if re.match(r"^(subdistrict|barrio|quartiere|quartier|ortsteil|bairro|buurt)\b", low):
            area = line.split(" ", 1)[1] if " " in line else line
        elif re.match(r"^(district|distrito|distretto|bezirk|zona|wijk)\b", low):
            district = line.split(" ", 1)[1] if " " in line else line
        elif city is None:
            city = line
        else:
            region = line
    return {
        "address": address,
        "area": area,
        "district": district,
        "city": city,
        "region": region,
        "lines": lines,
        "latitude": lat,
        "longitude": lng,
    }


def _parse_gallery(html):
    pics = _js_array(html, "fullScreenGalleryPics")
    photos, plans = [], []
    for pic in pics:
        if not isinstance(pic, dict):
            continue
        item = {
            "id": pic.get("multimediaId"),
            "link": pic.get("imageDataService") or pic.get("imageDataServiceWebp"),
            "tag": _clean(pic.get("tag") or pic.get("hoverText")),
            "title": _clean(pic.get("title")),
            "width": pic.get("width"),
            "height": pic.get("height"),
            "is_made_by_idealista": bool(pic.get("isMadeByIdealista")),
        }
        (plans if pic.get("isPlan") else photos).append(item)
    extra_plans = _js_array(html, "plans")
    if not plans and extra_plans:
        plans = [{"id": p.get("multimediaId"), "link": p.get("imageDataService") or p.get("imageDataServiceWebp"),
                  "tag": _clean(p.get("hoverText")), "title": _clean(p.get("title")), "width": p.get("width"),
                  "height": p.get("height"), "is_made_by_idealista": bool(p.get("isMadeByIdealista"))}
                 for p in extra_plans if isinstance(p, dict)]
    videos = [{"link": v.get("src"), "hd_link": v.get("hdSrc"), "thumbnail": v.get("thumbnail"),
               "is_made_by_idealista": bool(v.get("isMadeByIdealista"))}
              for v in _js_array(html, "videos") if isinstance(v, dict)]
    tours_3d = [t for t in _js_array(html, "visit3DTourURL") if isinstance(t, str)]
    virtual = [t for t in _js_array(html, "virtualTour360URL") if isinstance(t, str)]
    staging = [{"id": s.get("multimediaId"), "link": s.get("imageDataService") or s.get("imageDataServiceWebp"),
                "tag": _clean(s.get("hoverText")), "title": _clean(s.get("title"))}
               for s in _js_array(html, "homeStaging") if isinstance(s, dict)]
    return photos, plans, videos, tours_3d, virtual, staging


def _parse_description(soup, language):
    block = soup.select_one(".comment .adCommentsLanguage") or soup.select_one(".comment")
    if block is None:
        return None
    warning = block.select_one(".translationWarning")
    original = None
    if warning:
        link = warning.select_one("[data-lang]")
        original = _clean(link.get("data-lang")) if link else None
        warning.extract()
    text = block.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() or None
    return {"text": text, "language": language, "is_translated": warning is not None,
            "original_language": original}


def _parse_price_block(soup):
    """The 'Price' box: property price, price per m², community costs, the
    'also for rent' line."""
    box = soup.select_one(".price-features__container")
    if box is None:
        return {}
    out = {}
    for row in box.select("li, p, div"):
        text = _text(row)
        if not text or ":" not in text:
            continue
        label, value = [p.strip() for p in text.split(":", 1)]
        low = label.lower()
        if re.search(r"community|comunidad|condominio|charges|hausgeld|condomínio", low):
            out["community_costs"] = parse_price(value)
        elif re.search(r"per m²|por m²|al m²|au m²|pro m²", low):
            out["price_per_m2"] = parse_int(value)
        elif re.search(r"deposit|fianza|cauzione|caution|kaution", low):
            out["deposit"] = parse_price(value)
    also = box.find(string=re.compile(r"also for rent|también en alquiler|anche in affitto|également à louer|auch zu vermieten", re.I))
    if also:
        out["also_for_rent"] = parse_price(_text(also.parent))
    return out


_ADVERTISER_KIND_RE = re.compile(
    r"professional|profesional|professionista|professionnel|gewerblich|profissional|professioneel|"
    r"private|particular|privato|particulier|privat|advertiser|anunciante|inserzionista|annonceur|"
    r"anbieter|anunciante|adverteerder|verified|verificado|verificat|vérifié|verifiziert|geverifieerd", re.I)


def _parse_advertiser(soup, config, country):
    kind_node = soup.select_one(".professional-name")
    kind_text = _text(kind_node).lower()
    is_professional = bool(re.search(r"professional|profesional|professionista|professionnel|gewerblich|profissional|professioneel", kind_text))
    is_private = bool(re.search(r"private owner|particular|privato|particulier|privatanbieter|proprietário|particuliere", kind_text))
    about = soup.select_one("a.about-advertiser-name")
    slug = None
    if about:
        match = refs._LINK_AGENCY_RE.search(about.get("href") or "")
        slug = match.group(1) if match else None
    logo = soup.select_one(".advertiser-logo img, .agency-video__logo")
    verified = bool(re.search(r"\bverified\b|verificado|verificat|vérifié|verifiziert|geverifieerd", kind_text))
    agency = None
    if slug or about:
        agency = {
            "name": _clean(config.get("adCommercialName")) or (_clean(about.get("title")) if about else None) or _text(about) or None,
            "slug": slug,
            "link": refs.agency_link(country, slug) if slug else None,
            "logo": _clean(logo.get("src") or logo.get("data-ondemand-img")) if logo else None,
        }
    # The name printed next to the advertiser kind, unless it is only the
    # kind label itself ("Professional advertiser Verified").
    printed = None
    name_node = soup.select_one(".professional-name span") or soup.select_one(".advertiser-name")
    if name_node:
        candidate = _text(name_node)
        if candidate and not _ADVERTISER_KIND_RE.search(candidate):
            printed = candidate
    name = printed or _clean(config.get("adProfessionalName")) or _clean(config.get("adCommercialName")) \
        or _clean(config.get("adFirstName"))
    return {
        "type": "professional" if (is_professional or agency) else ("private" if is_private else None),
        "name": name,
        "is_verified": verified,
        "agency": agency,
    }


def parse_detail(html, country, property_id=None, language="en", today=None):
    """A listing page -> the full record. Raises ValueError on a page that is
    not a listing (the caller maps a dead id to NotFound before this)."""
    soup = _soup(html)
    config = parse_config(html)
    ad_id = str(config.get("adId") or property_id or "").strip() or None
    if not ad_id or not soup.select_one(".main-info__title-main, .info-data"):
        raise ValueError("not a listing page")
    title = _text(soup.select_one(".main-info__title-main")) or None
    subtitle = _text(soup.select_one(".main-info__title-minor")) or None
    price_node = soup.select_one(".info-data-price")
    price = parse_price(_text(price_node)) if price_node else None
    if price is None and isinstance(config.get("buyingPrice"), (int, float)) and config.get("buyingPrice"):
        price = {"amount": int(config["buyingPrice"]), "currency": "EUR",
                 "period": "month" if config.get("operation") == "rent" else None, "text": None}
    per_m2 = parse_int(_text(soup.select_one(".info-data-price-by-area")))
    price_block = _parse_price_block(soup)
    sections = _feature_sections(soup)
    lines = _all_feature_lines(sections)
    facts = _parse_lines(lines)
    header_spans = [_text(s) for s in soup.select(".info-features > span")]
    header_spans = [s for s in header_spans if s]
    if facts["size_m2"] is None:
        for span in header_spans:
            match = _SIZE_RE.search(span)
            if match:
                facts["size_m2"] = parse_int(match.group(1))
                break
    if facts["rooms"] is None:
        for span in header_spans:
            match = _ROOMS_RE.search(span)
            if match and "m²" not in span:
                facts["rooms"] = int(match.group(1))
                break
    if facts["floor"] is None:
        for span in header_spans:
            if _FLOOR_RE.search(span.lower()) and "m²" not in span:
                floor = _parse_floor(span)
                facts["floor"], facts["is_exterior"], facts["has_lift"] = floor["text"], floor["is_exterior"], floor["has_lift"]
                break
    tags = [_text(t) for t in soup.select(".detail-info-tags .tag")]
    photos, plans, videos, tours_3d, virtual, staging = _parse_gallery(html)
    typology = _clean(config.get("typology"))
    operation = _clean(config.get("operation"))
    updated = _text(soup.select_one(".stats-text")) or None
    reference = _text(soup.select_one(".txt-ref")) or _clean(config.get("adExternalReference"))
    advertiser = _parse_advertiser(soup, config, country)
    is_new_dev = bool(facts["is_new_development"] or re.search(r"isNewDevelopmentAd:\s*'[^']+'\s*!==\s*''", html or ""))
    return {
        "id": ad_id,
        "link": refs.property_link(country, ad_id),
        "title": title,
        "subtitle": subtitle,
        "operation": operation,
        "property_type": _public_type(typology),
        "typology": typology,
        "price": price,
        "price_per_m2": per_m2 or price_block.get("price_per_m2"),
        "community_costs": price_block.get("community_costs"),
        "deposit": price_block.get("deposit"),
        "also_for_rent": price_block.get("also_for_rent"),
        "is_price_on_request": bool(config.get("isPriceOnRequest")),
        "size_m2": facts["size_m2"],
        "usable_size_m2": facts["usable_size_m2"],
        "plot_size_m2": facts["plot_size_m2"],
        "rooms": facts["rooms"],
        "bathrooms": facts["bathrooms"],
        "floor": facts["floor"],
        "is_exterior": facts["is_exterior"],
        "has_lift": facts["has_lift"],
        "condition": facts["condition"],
        "year_built": facts["year_built"],
        "orientation": facts["orientation"],
        "heating": facts["heating"],
        "parking": facts["parking"],
        "is_furnished": facts["is_furnished"],
        "has_terrace": facts["has_terrace"],
        "has_balcony": facts["has_balcony"],
        "has_garden": facts["has_garden"],
        "has_swimming_pool": facts["has_swimming_pool"],
        "has_air_conditioning": facts["has_air_conditioning"],
        "has_storage_room": facts["has_storage_room"],
        "has_wardrobes": facts["has_wardrobes"],
        "is_accessible": facts["is_accessible"],
        "is_new_development": is_new_dev,
        "is_offmarket": bool(config.get("isOffmarket")),
        "is_holiday_rental": bool(config.get("isVacational")),
        "has_online_booking": bool(config.get("hasOnlineBooking")),
        "tags": tags,
        "features": sections,
        "energy_certificate": _parse_energy(soup, lines),
        "description": _parse_description(soup, language),
        "location": {**_parse_location(soup, html), "location_id": _clean(config.get("locationId"))},
        "photos": photos,
        "photos_count": len(photos) if photos else None,
        "floor_plans": plans,
        "videos": videos,
        "tours_3d": tours_3d,
        "virtual_tours": virtual,
        "home_staging": staging,
        "reference": reference,
        "updated_text": updated,
        "updated_date": parse_update_date(updated, today),
        "advertiser": advertiser,
    }


def parse_multimedia(payload, country=None):
    """listingOnDemandMultimedias JSON -> {"photos", "floor_plans", "videos",
    "tours_3d", "home_staging"} (links absolute)."""
    out = {"photos": [], "floor_plans": [], "videos": [], "tours_3d": [], "home_staging": []}
    groups = ((payload or {}).get("data") or {}).get("multimedias") or []
    keys = {"PICTURE": "photos", "PLAN": "floor_plans", "VIDEO": "videos", "VIRTUAL_TOUR_3D": "tours_3d",
            "HOME_STAGING": "home_staging"}
    for group in groups:
        if not isinstance(group, dict):
            continue
        key = keys.get(group.get("type"))
        if not key:
            continue
        for item in group.get("content") or []:
            if not isinstance(item, dict):
                continue
            src = item.get("src") or ""
            link = src if src.startswith("http") else (MULTIMEDIA_BASE + src if src else None)
            out[key].append({"id": item.get("id"), "link": link, "tag": _clean(item.get("description"))})
    return out


# ---- agency microsite ---------------------------------------------------------------

def parse_agency(html, country, slug=None):
    """The /pro/<slug>/ microsite -> the profile record (+ its listing page)."""
    soup = _soup(html)
    config = parse_config(html)
    name = _text(soup.select_one("#commercial-name")) or _clean(config.get("commercialName"))
    if not name:
        raise ValueError("not an agency page")
    info = soup.select_one("#office-info")
    properties_count = since_year = quality = None
    if info:
        head = info.select_one(".office-title p")
        head_text = _text(head)
        for piece in re.split(r"\s*[·|]\s*", head_text):
            low = piece.lower()
            year = _YEAR_RE.search(piece)
            if re.search(r"since|desde|dal|depuis|seit|sinds", low) and year:
                since_year = int(year.group(1))
            elif properties_count is None:
                properties_count = parse_int(piece)
        for p in info.select("p"):
            text = _text(p)
            match = _PERCENT_RE.search(text)
            if match and re.search(r"quality|calidad|qualit", text, re.I):
                quality = int(match.group(1))
    description = _text(soup.select_one(".office-description")) or None
    address_parts = [_text(s) for s in soup.select("#office-info .location .location-text")]
    address = ", ".join(p.strip(", ") for p in address_parts if p.strip(", ")) or None
    languages_text = _text(soup.select_one("#languages"))
    languages = None
    if languages_text:
        body = re.sub(r"^(speaks|habla|parla|parle|spricht|fala|spreekt)\s+", "", languages_text, flags=re.I)
        languages = [l.strip() for l in re.split(r",|\band\b|\by\b|\be\b|\bet\b|\bund\b|&", body) if l.strip()]
    image = soup.select_one("#office-image")
    logo = soup.select_one(".agency-video__logo, .office-logo img")
    if logo is None:
        # the microsite shows no logo of its own; its listing cards carry it
        for branding in soup.select(".logo-branding a[href]"):
            match = refs._LINK_AGENCY_RE.search(branding.get("href") or "")
            if match and (not slug or match.group(1) == slug or not config.get("micrositeName")):
                logo = branding.select_one("img")
                break
    trademarks = [_text(p) for p in soup.select("#office-main-trademarks p") if _text(p)]
    locations = []
    seen = set()
    for a in soup.select("a[data-location-id]"):
        loc_id = a.get("data-location-id")
        if not loc_id or loc_id in seen:
            continue
        seen.add(loc_id)
        locations.append({"name": _clean(a.get("title")) or _text(a), "id": loc_id,
                          "link": _absolute(country, _strip_locale(a.get("href")))})
    slug = slug or _clean(config.get("micrositeName"))
    listing_url = _clean(config.get("listingSearchUrl"))
    return {
        "slug": slug,
        "name": name,
        "link": refs.agency_link(country, slug) if slug else None,
        "properties_count": properties_count,
        "since_year": since_year,
        "publication_quality_percent": quality,
        "description": description,
        "address": address,
        "languages": languages,
        "logo": _clean(logo.get("src") or logo.get("data-ondemand-img")) if logo else None,
        "image": _absolute(country, _clean(image.get("data-image-url"))) if image and image.get("data-image-url") else None,
        "video": _clean(config.get("commercialVideoUrlHD") or config.get("commercialVideoUrl")),
        "registrations": trademarks,
        "locations": locations,
        "default_listing_link": _absolute(country, _strip_locale(listing_url)) if listing_url else None,
        "total_listing_pages": parse_int(config.get("totalPages")),
        "commercial_data_id": _clean(config.get("commercialDataId")),
    }


# ---- agencies directory ---------------------------------------------------------------

def parse_directory(html, country):
    """/agencias-inmobiliarias/<location>/inmobiliarias -> the featured
    agency cards of a location."""
    soup = _soup(html)
    cards = []
    for card in soup.select("article.zone-experts-agency-card"):
        name_node = card.select_one(".agency-name a")
        href = name_node.get("href") if name_node else card.get("data-microsite-url")
        slug_match = refs._LINK_AGENCY_RE.search(href or "")
        slug = slug_match.group(1) if slug_match else None
        years = None
        secondary = _text(card.select_one(".agency-name .secondary-text"))
        if secondary:
            years = parse_int(secondary)
        onsale = card.select_one(".property-onsale")
        listings_count = parse_int(_text(onsale.select_one("strong"))) if onsale and onsale.select_one("strong") else None
        price_range = None
        range_node = card.select_one("[itemprop=priceRange]")
        if range_node:
            numbers = [parse_int(n) for n in re.findall(r"[\d.,   ]+", _text(range_node))]
            numbers = [n for n in numbers if n]
            if len(numbers) >= 2:
                price_range = {"min": numbers[0], "max": numbers[1], "currency": "EUR"}
        quality = reports = reports_total = first_page = None
        for node in card.select(".agency-card-info p, .agency-card-info span"):
            text = _text(node)
            if not text:
                continue
            strong = node.select_one("strong")
            value = parse_int(_text(strong)) if strong else None
            if "%" in text and quality is None:
                quality = value
            elif re.search(r"photographic|fotográf|fotograf|reportage", text, re.I) and reports is None:
                reports = value
            elif re.search(r"total of|de un total|di un totale|d'un total|insgesamt", text, re.I):
                reports_total = value
            elif re.search(r"1st page|first page|primera página|prima pagina|1ère page|ersten seite", text, re.I):
                first_page = value
        logo = card.select_one(".zone-experts-agency-logo img")
        pictures = [_clean(img.get("src")) for img in card.select(".images-list img") if img.get("src")]
        cards.append({
            "id": _clean(card.get("data-agency-id")),
            "slug": slug,
            "name": _text(name_node) or None,
            "link": refs.agency_link(country, slug) if slug else None,
            "listings_link": _absolute(country, _strip_locale(href)) if href else None,
            "logo": _clean(logo.get("src")) if logo else None,
            "years_on_site": years,
            "operation": (_clean(card.get("data-operation-id")) or "").lower() or None,
            "listings_count": listings_count,
            "listings_text": _text(onsale) or None,
            "price_range": price_range,
            "publication_quality_percent": quality,
            "verified_reports": reports,
            "reports_last_3_months": reports_total,
            "first_page_listings": first_page,
            "speaks_your_language": card.select_one(".lang-tag") is not None,
            "location_id": _clean(card.get("data-location-id")),
            "sample_pictures": pictures,
        })
    title = soup.select_one("h1")
    return {"title": _text(title) or None, "results": cards}


def parse_directory_index(html, country):
    """The agencies directory index -> [{"name", "slug", "link"}] of the
    locations it links (province and city pages)."""
    soup = _soup(html)
    out, seen = [], set()
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        match = re.search(r"/(?:agencias-inmobiliarias|agenzie-immobiliari)/([^#?]+?)/(?:inmobiliarias|agenzie-immobiliari)/?$", href)
        if not match:
            continue
        slug = match.group(1).strip("/")
        if slug in seen:
            continue
        seen.add(slug)
        out.append({"name": _text(a) or None, "slug": slug,
                    "link": _absolute(country, _strip_locale(href))})
    return out


# ---- typeahead ------------------------------------------------------------------------

def parse_suggestions(payload, country):
    """locationsSuggest JSON -> clean location rows."""
    out = []
    for row in payload or []:
        if not isinstance(row, dict):
            continue
        text = html_module.unescape(re.sub(r"<[^>]+>", "", row.get("text") or ""))
        url = row.get("url") or ""
        try:
            _segment, slug, _filters, _page = refs.split_listing_path(country, _strip_locale(url))
        except ValueError:
            slug = None
        out.append({
            "name": _clean(text),
            "id": row.get("locationId"),
            "slug": slug,
            "link": _absolute(country, _strip_locale(url)) if url else None,
            "type": _clean(row.get("category")),
            "parent_id": row.get("parentLocationId"),
            "listings_count": parse_int(row.get("count")),
            "has_child_zones": row.get("hasChildZones"),
            "is_zone_of_interest": bool(row.get("zoneOfInterest")),
            "is_postcode": bool(row.get("seekablePostalCode")) or (_clean(row.get("category")) or "").lower() in ("postcode", "código postal", "cap", "code postal"),
        })
    return out
