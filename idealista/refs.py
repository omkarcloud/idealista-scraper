"""Reference resolvers, site/path tables and URL builders for /idealista/*.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url` / `id` pair):

    property   the numeric ad id (109630900) OR any idealista listing link
               (www.idealista.com/inmueble/<id>/, www.idealista.it/immobile/<id>/,
               with or without a locale prefix)
    agency     the microsite slug (walterhauschamberi) OR any /pro/<slug>/ link
    location   a place name ("Chamberí, Madrid"), a location slug from
               locations/search ("madrid-madrid", "madrid/chamberi"), a postcode,
               OR any idealista search link — api.py resolves names through
               the site's own typeahead; the schema only classifies the form
    shape      a polygon ("lat,lng;lat,lng;…", 3+ points) OR a drawn-area link
               (…/areas/…?shape=((polyline)))

Markets (2026-10-30): Spain (www.idealista.com) and Italy (www.idealista.it).
Portugal (www.idealista.pt) sits behind a Cloudflare challenge on every curl
profile and exit (research 2026-10-30), so a .pt link is refused with a
plain message rather than served a block.

Path words are the site's own URL grammar, captured from the filter forms of
the Madrid and Milan listing pages on 2026-10-30 (the `data-filter-href`
links): the operation+vertical segment, the detail segment, the agency
directory, the page-number segment and the sort parameter all differ per
market, the `adfilter_*` query parameters do not.
"""
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

# ---- markets ----------------------------------------------------------------------

SITES = {
    "es": "https://www.idealista.com",
    "it": "https://www.idealista.it",
}
DEFAULT_COUNTRY = "es"

# Locales the site renders with a /<lang>/ prefix. Spanish (and Catalan) are
# missing on purpose: DataDome refuses the es / ca renderings of
# www.idealista.com to every curl identity on every exit (research
# 2026-10-30), while the other locales pass — so the descriptions come back
# in one of these, auto-translated by the site. Italian is idealista.it's
# own default (no prefix there).
LANGUAGES = ("en", "fr", "de", "it", "pt", "nl", "ru")
DEFAULT_LANGUAGE = "en"
HOST_DEFAULT_LANGUAGE = {"es": "es", "it": "it"}

# Public property_type -> the site's typeahead typology key. The listing
# path segments per (country, operation, typology) are below.
PROPERTY_TYPES = {
    "homes": "home",
    "rooms": "room",
    "new_developments": "newdevelopment",
    "offices": "office",
    "premises": "warehouse",
    "transfers": "transfer",
    "garages": "garage",
    "lands": "land",
    "storage_rooms": "storageroom",
    "buildings": "building",
}
OPERATIONS = ("sale", "rent")

# (country, operation, typology) -> listing path segment. Rooms are rent-only,
# transfers sale-only, new developments sale-only (the site has no other
# pages for them).
_LISTING_SEGMENT = {
    "es": {
        ("sale", "home"): "venta-viviendas", ("rent", "home"): "alquiler-viviendas",
        ("rent", "room"): "alquiler-habitacion",
        ("sale", "newdevelopment"): "venta-obranueva",
        ("sale", "office"): "venta-oficinas", ("rent", "office"): "alquiler-oficinas",
        ("sale", "warehouse"): "venta-locales", ("rent", "warehouse"): "alquiler-locales",
        ("sale", "transfer"): "traspasos",
        ("sale", "garage"): "venta-garajes", ("rent", "garage"): "alquiler-garajes",
        ("sale", "land"): "venta-terrenos", ("rent", "land"): "alquiler-terrenos",
        ("sale", "storageroom"): "venta-trasteros", ("rent", "storageroom"): "alquiler-trasteros",
        ("sale", "building"): "venta-edificios", ("rent", "building"): "alquiler-edificios",
    },
    "it": {
        ("sale", "home"): "vendita-case", ("rent", "home"): "affitto-case",
        ("rent", "room"): "affitto-stanze",
        ("sale", "newdevelopment"): "vendita-nuove_costruzioni",
        ("sale", "office"): "vendita-uffici", ("rent", "office"): "affitto-uffici",
        ("sale", "warehouse"): "vendita-negozi", ("rent", "warehouse"): "affitto-negozi",
        ("sale", "transfer"): "cessione-attivita",
        ("sale", "garage"): "vendita-garage", ("rent", "garage"): "affitto-garage",
        ("sale", "land"): "vendita-terreni", ("rent", "land"): "affitto-terreni",
        ("sale", "storageroom"): "vendita-cantine", ("rent", "storageroom"): "affitto-cantine",
        ("sale", "building"): "vendita-edifici", ("rent", "building"): "affitto-edifici",
    },
}
DETAIL_SEGMENT = {"es": "inmueble", "it": "immobile"}
_LINK_DETAIL_SEGMENTS = ("inmueble", "immobile", "imovel")
PAGE_SEGMENT = {"es": "pagina", "it": "lista"}        # /pagina-2.htm | /lista-2.htm
SORT_PARAM = {"es": "ordenado-por", "it": "ordine"}
AREAS_SEGMENT = {"es": "areas", "it": "aree"}
_MAP_SEGMENTS = ("mapa", "mapa-google", "mappa", "lista-mappa")   # the map view of a listing page
POSTCODE_SEGMENT = {"es": "codigo-postal", "it": "cap"}
AGENCIES_DIRECTORY = {"es": ("agencias-inmobiliarias", "inmobiliarias"),
                      "it": ("agenzie-immobiliari", "agenzie-immobiliari")}

# Public sort -> the site's value per market (same words on both sites except
# the Spanish price-per-m² pair, which idealista.it does not offer).
SORTS = {
    "price_asc": {"es": "precios-asc", "it": "prezzi-asc"},
    "price_desc": {"es": "precios-desc", "it": "prezzi-desc"},
    "newest": {"es": "fecha-publicacion-desc", "it": "pubblicazione-desc"},
    "oldest": {"es": "fecha-publicacion-asc", "it": "pubblicazione-asc"},
    "size_asc": {"es": "area-asc", "it": "area-asc"},
    "size_desc": {"es": "area-desc", "it": "area-desc"},
    "floor_asc": {"es": "planta-asc", "it": "piano-asc"},
    "floor_desc": {"es": "planta-desc", "it": "piano-desc"},
    "price_per_m2_asc": {"es": "precio-metro-cuadrado-asc"},
    "price_per_m2_desc": {"es": "precio-metro-cuadrado-desc"},
    "price_drop": {"es": "rebajas-desc", "it": "queda-desc"},
}

# Public filter values -> the site's adfilter_* query parameters (name, value).
# Discovered 2026-10-30 by submitting each form field of the Madrid sale /
# rent pages and reading the canonical link the server answered with
# (con-precio-hasta_300000, con-ascensor, ...); the server applies them
# straight from the query string, so no slug table is needed.
HOME_TYPES = {
    "flat": ("adfilter_onlyflats", "1"), "penthouse": ("adfilter_penthouse", "1"),
    "duplex": ("adfilter_duplex", "1"), "house": ("adfilter_chalets", "2"),
    "detached": ("adfilter_independent", "4"), "semi_detached": ("adfilter_semidetached", "3"),
    "terraced": ("adfilter_terraced", "2"), "country_house": ("adfilter_countryhouses", "3"),
    "apartment": ("adfilter_apartment", "1"), "villa": ("adfilter_villalabel", "1"),
    "loft": ("adfilter_loft", "1"), "single_storey": ("adfilter_casabaja", "1"),
    "attic": ("adfilter_atticstudio", "1"),
}
CONDITIONS = {
    "new_build": ("adfilter_newconstruction", "1"), "good": ("adfilter_goodcondition", "3"),
    "needs_renovation": ("adfilter_toberestored", "2"),
}
FEATURES = {
    "air_conditioning": ("adfilter_hasairconditioning", "1"), "wardrobes": ("adfilter_wardrobes", "1"),
    "lift": ("adfilter_lift", "1"), "balcony": ("adfilter_balcony", "1"),
    "terrace": ("adfilter_hasterrace", "1"), "balcony_or_terrace": ("adfilter_exterior_domestic_space_type", "1"),
    "exterior": ("adfilter_flatlocation", "1"), "parking": ("adfilter_parkingspace", "1"),
    "garden": ("adfilter_garden", "1"), "swimming_pool": ("adfilter_swimmingpool", "1"),
    "storage_room": ("adfilter_boxroom", "1"), "accessible": ("adfilter_accessibleHousing", "1"),
    "luxury": ("adfilter_luxury", "1"), "floor_plan": ("adfilter_hasplan", "1"),
    "virtual_tour": ("adfilter_digitalvisit", "1"), "bank_owned": ("adfilter_agencyisabank", "1"),
    "pets_allowed": ("adfilter_housingpetsallowed", "1"),
    "long_term": ("adfilter_longTermRental", "1"), "short_term": ("adfilter_seasonalRental", "1"),
}
FURNISHED = {"furnished": ("adfilter_amenity", "3"), "kitchen_only": ("adfilter_amenity", "2")}
FLOORS = {
    "top": ("adfilter_top_floor", "1"), "middle": ("adfilter_intermediate_floor", "2"),
    "ground": ("adfilter_ground_floor", "3"),
}
ENERGY_RATINGS = {
    "high": ("adfilter_energyCertificateHigh", "1"), "medium": ("adfilter_energyCertificateMedium", "1"),
    "low": ("adfilter_energyCertificateLow", "1"),
}
OCCUPANCY = {
    "free": ("adfilter_free", "1"), "tenanted": ("adfilter_tenanted", "1"),
    "bare_ownership": ("adfilter_bareOwnership", "1"), "squatted": ("adfilter_illegallyOccupied", "1"),
}
# Sale pages: 1 = last 48 h; rent pages use 4 for the same window.
PUBLISHED = {"last_48_hours": {"sale": "1", "rent": "4"}, "last_week": {"sale": "2", "rent": "2"},
             "last_month": {"sale": "3", "rent": "3"}}
BEDROOMS = ("0", "1", "2", "3", "4")      # 0 = studio, 4 = four or more
BATHROOMS = ("1", "2", "3")               # 3 = three or more

MAX_PAGES = 60          # the site serves page 1 again past page 60 (research 2026-10-30)
ITEMS_PER_PAGE = 30
DIRECTORY_ITEMS_PER_PAGE = 15   # agencies directory cards per page


# ---- link helpers ------------------------------------------------------------------

_ID_RE = re.compile(r"^[0-9]{5,12}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_LINK_DETAIL_RE = re.compile(r"/(?:inmueble|immobile|imovel)/([0-9]{5,12})(?:/|$)")
_LINK_AGENCY_RE = re.compile(r"/pro/([a-z0-9][a-z0-9_-]*)(?:/|$)")
_LANG_PREFIX_RE = re.compile(r"^/([a-z]{2})(?=/)")


def _is_link(value):
    return value.startswith(("http://", "https://", "//", "www.idealista."))


def _as_url(value):
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("www."):
        return "https://" + value
    return value


def country_of_host(host):
    """'www.idealista.it' -> 'it'; None for a host that is not idealista."""
    host = (host or "").lower()
    match = re.match(r"^(?:www\.)?idealista\.([a-z]{2,3})$", host)
    if not match:
        return None
    tld = match.group(1)
    return {"com": "es", "es": "es", "it": "it", "pt": "pt"}.get(tld)


def parse_site_link(value):
    """An idealista link -> (country, path without the locale prefix, query
    dict). Raises ValueError for other hosts and for the Portuguese market."""
    url = urlparse(_as_url(value))
    country = country_of_host(url.hostname)
    if country is None:
        raise ValueError("Must be an idealista.com or idealista.it link.")
    if country == "pt":
        raise ValueError("idealista.pt is not supported (Spain and Italy only).")
    path = unquote(url.path or "/")
    path = _LANG_PREFIX_RE.sub("", path) or "/"
    query = {k: v[-1] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
    return country, path, query


def resolve_property(value):
    """Bare ad id OR an idealista listing link -> the ad id (digits)."""
    value = (value or "").strip()
    if _ID_RE.match(value):
        return value
    if _is_link(value):
        _country, path, _query = parse_site_link(value)
        match = _LINK_DETAIL_RE.search(path)
        if match:
            return match.group(1)
        raise ValueError("Must be an idealista listing link "
                         "(https://www.idealista.com/inmueble/<id>/).")
    raise ValueError("Must be a numeric idealista listing id (109630900) or a listing link.")


def property_country(value, default=DEFAULT_COUNTRY):
    """The market a `property` value names: the link's host, else `default`."""
    value = (value or "").strip()
    if _is_link(value):
        try:
            return parse_site_link(value)[0]
        except ValueError:
            return default
    return default


def resolve_agency(value):
    """Bare microsite slug OR a /pro/<slug>/ link -> the slug."""
    value = (value or "").strip()
    if _is_link(value):
        _country, path, _query = parse_site_link(value)
        match = _LINK_AGENCY_RE.search(path)
        if match:
            return match.group(1)
        raise ValueError("Must be an idealista agency link (https://www.idealista.com/pro/<slug>/).")
    slug = value.lower()
    if _SLUG_RE.match(slug) and len(slug) <= 120:
        return slug
    raise ValueError("Must be an idealista agency slug (walterhauschamberi) or a /pro/<slug>/ link.")


def agency_country(value, default=DEFAULT_COUNTRY):
    return property_country(value, default)


# ---- locations --------------------------------------------------------------------

def classify_location(value):
    """A `location` value -> ("link", (country, path, query)) | ("slug", slug) |
    ("name", text). A slug is the site's own location path (madrid-madrid,
    madrid/chamberi, barcelona/ciutat-vella/la-barceloneta); anything else
    with spaces, capitals or accents is a name for the typeahead."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must not be empty.")
    if _is_link(value):
        return "link", parse_site_link(value)
    slug = value.strip("/")
    if slug and not slug.isdigit() and all(_SLUG_RE.match(part) for part in slug.split("/")) \
            and len(slug.split("/")) <= 4:
        return "slug", slug
    if len(value) > 120:
        raise ValueError("Location name too long (max 120 characters).")
    return "name", value


def listing_segment(country, operation, typology):
    """The operation+vertical path segment; ValueError when the site has no
    such page (rooms for sale, transfers for rent, ...)."""
    segment = _LISTING_SEGMENT[country].get((operation, typology))
    if not segment:
        raise ValueError(f"idealista has no '{operation}' pages for this property type.")
    return segment


def split_listing_path(country, path):
    """A listing path (locale prefix already removed) -> (segment, location
    slug, filter segment, page). '/venta-viviendas/madrid-madrid/con-ascensor/
    pagina-2.htm' -> ('venta-viviendas', 'madrid-madrid', 'con-ascensor', 2).
    Raises ValueError when the path is not a listing page."""
    parts = [p for p in path.strip("/").split("/") if p]
    if parts and parts[-1] in _MAP_SEGMENTS:            # the map view of the same search
        parts = parts[:-1]
    if not parts:
        raise ValueError("Not an idealista search link.")
    page = 1
    page_match = re.match(rf"^{PAGE_SEGMENT[country]}-(\d+)(?:\.htm)?$", parts[-1])
    if page_match:
        page = int(page_match.group(1))
        parts = parts[:-1]
    if not parts:
        raise ValueError("Not an idealista search link.")
    known = set(_LISTING_SEGMENT[country].values())
    segment = parts[0]
    geo = False
    if segment == "geo" and len(parts) > 1:      # /geo/venta-viviendas/codigo-postal-28013/
        geo = True
        parts = parts[1:]
        segment = parts[0]
    if segment not in known:
        raise ValueError("Not an idealista search link (expected a listing page such as "
                         "/venta-viviendas/madrid-madrid/).")
    rest = parts[1:]
    filters = None
    if rest and rest[-1].startswith("con-"):
        filters = rest[-1]
        rest = rest[:-1]
    location = "/".join(rest)
    if geo:
        location = "geo/" + location
    return segment, location, filters, page


def locale_prefix(country, language):
    """'/en' for a locale the host renders with a prefix; '' for the host's
    own default language."""
    if not language or language == HOST_DEFAULT_LANGUAGE.get(country):
        return ""
    return "/" + language


def listing_path(country, language, segment, location, filters=None, page=1):
    """'/en/venta-viviendas/madrid-madrid/con-ascensor/pagina-2.htm'. A
    postcode location from the typeahead ('geo/codigo-postal-28013') lives
    under /geo/<segment>/… on the site."""
    location = location.strip("/")
    if location.startswith("geo/"):
        path = f"{locale_prefix(country, language)}/geo/{segment}/{location[4:]}/"
    else:
        path = f"{locale_prefix(country, language)}/{segment}/{location}/"
    if filters:
        path += filters.strip("/") + "/"
    if page and page > 1:
        path += f"{PAGE_SEGMENT[country]}-{page}.htm"
    return path


def areas_path(country, language, segment, page=1):
    """'/en/areas/venta-viviendas/' (+ 'pagina-2' without .htm past page 1)."""
    path = f"{locale_prefix(country, language)}/{AREAS_SEGMENT[country]}/{segment}/"
    if page and page > 1:
        path += f"{PAGE_SEGMENT[country]}-{page}"
    return path


def detail_path(country, language, property_id):
    return f"{locale_prefix(country, language)}/{DETAIL_SEGMENT[country]}/{property_id}/"


def agency_path(country, language, slug, segment=None, location=None, page=1):
    path = f"{locale_prefix(country, language)}/pro/{slug}/"
    if segment:
        path += segment + "/"
        if location:
            path += location.strip("/") + "/"
        if page and page > 1:
            path += f"{PAGE_SEGMENT[country]}-{page}.htm"
    return path


def directory_path(country, language, location, page=1):
    head, tail = AGENCIES_DIRECTORY[country]
    path = f"{locale_prefix(country, language)}/{head}/{location.strip('/')}/{tail}"
    if page and page > 1:
        path += f"/{PAGE_SEGMENT[country]}-{page}.htm"
    return path


def suggest_path(country, language, operation, typology, text):
    return f"{locale_prefix(country, language)}/locationsSuggest/{operation}/{typology}/{quote(text, safe='')}"


def multimedia_path(property_id):
    return f"/listingOnDemandMultimedias/{property_id}"


def absolute(country, path):
    return SITES[country] + path


def property_link(country, property_id):
    return absolute(country, f"/{DETAIL_SEGMENT[country]}/{property_id}/")


def agency_link(country, slug):
    return absolute(country, f"/pro/{slug}/")


# ---- shapes (drawn areas) ------------------------------------------------------------
# The site encodes a drawn polygon as a Google encoded polyline (1e-5
# precision) wrapped in double parentheses: ?shape=((ykzuFfilUsf@_sB...)).

_POINT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def _encode_value(value):
    value = ~(value << 1) if value < 0 else value << 1
    out = ""
    while value >= 0x20:
        out += chr((0x20 | (value & 0x1f)) + 63)
        value >>= 5
    return out + chr(value + 63)


def encode_polyline(points):
    """[(lat, lng), ...] -> Google encoded polyline (1e-5 precision)."""
    out, last_lat, last_lng = "", 0, 0
    for lat, lng in points:
        ilat, ilng = round(lat * 1e5), round(lng * 1e5)
        out += _encode_value(ilat - last_lat) + _encode_value(ilng - last_lng)
        last_lat, last_lng = ilat, ilng
    return out


def decode_polyline(text):
    """Google encoded polyline -> [(lat, lng), ...]."""
    points, index, lat, lng = [], 0, 0, 0
    while index < len(text):
        for which in (0, 1):
            result, shift = 0, 0
            while True:
                if index >= len(text):
                    raise ValueError("Truncated polyline.")
                byte = ord(text[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += delta
            else:
                lng += delta
        points.append((lat / 1e5, lng / 1e5))
    return points


def resolve_shape(value):
    """'lat,lng;lat,lng;…' (3+ points; also newline / '|' / space separated)
    OR a drawn-area idealista link -> the site's ((polyline)) shape value."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must not be empty.")
    if _is_link(value):
        _country, _path, query = parse_site_link(value)
        shape = (query.get("shape") or "").strip()
        if not shape:
            raise ValueError("The link carries no ?shape= drawn area.")
        inner = shape.strip("()")
        try:
            points = decode_polyline(inner)
        except ValueError:
            raise ValueError("The link's ?shape= value is not a polyline.")
        if len(points) < 3:
            raise ValueError("The drawn area needs at least 3 points.")
        return f"(({inner}))"
    raw = value.replace("|", ";").replace("\n", ";")
    if ";" not in raw:
        raw = re.sub(r"\)\s*,?\s*\(", ";", raw).replace("(", "").replace(")", "")
        if ";" not in raw:
            raw = " ".join(raw.split()).replace(", ", ",").replace(" ", ";")
    points = []
    for piece in raw.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        match = _POINT_RE.match(piece)
        if not match:
            raise ValueError("Each point must be 'lat,lng' (e.g. 40.4168,-3.7038); separate points with ';'.")
        lat, lng = float(match.group(1)), float(match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError(f"Point out of range: {piece}.")
        points.append((lat, lng))
    if len(points) < 3:
        raise ValueError("A shape needs at least 3 'lat,lng' points.")
    if len(points) > 200:
        raise ValueError("At most 200 points.")
    return f"(({encode_polyline(points)}))"


def shape_points(shape):
    """The ((polyline)) shape value -> [{"latitude", "longitude"}, ...]."""
    return [{"latitude": lat, "longitude": lng} for lat, lng in decode_polyline(shape.strip("()"))]
