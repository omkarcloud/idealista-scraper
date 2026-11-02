"""The /idealista/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs). Caching happens here through
cache.cached_call, keyed on the validated params.

Shared upstream pages are cached once and sliced: the agency microsite
(agencies/details and agencies/properties page 1 of the agency's default
listing read the same parsed page), and a place name typed into
properties/search is resolved through the same cached typeahead answer that
locations/search serves.
"""
import math
import re
from urllib.parse import unquote

from cache import cached_call
from idealista import cache_config as ttl
from idealista import parsers, refs
from idealista.fetch import (IdealistaNotFound, fetch_agency, fetch_detail, fetch_directory,
                             fetch_listing_page, fetch_multimedia, fetch_suggest, is_zero_results)

ITEMS_PER_PAGE = refs.ITEMS_PER_PAGE


# ---- shared helpers --------------------------------------------------------------------

def _typology(property_type):
    return refs.PROPERTY_TYPES[property_type]


def _filter_params(data, country, operation):
    """The validated filter params -> the site's adfilter_* query dict."""
    query = {}
    if data.get("min_price"):
        query["adfilter_pricemin"] = str(data["min_price"])
    if data.get("max_price"):
        query["adfilter_price"] = str(data["max_price"])
    if data.get("min_size"):
        query["adfilter_area"] = str(data["min_size"])
    if data.get("max_size"):
        query["adfilter_areamax"] = str(data["max_size"])
    for bedrooms in data.get("bedrooms") or []:
        if bedrooms == "4":
            query["adfilter_rooms_4_more"] = "4"
            if country == "it":                      # idealista.it splits 4 and 5+
                query["adfilter_rooms_4"] = "4"
                query["adfilter_rooms_5_more"] = "5"
        else:
            query[f"adfilter_rooms_{bedrooms}"] = bedrooms
    for baths in data.get("bathrooms") or []:
        query[f"adfilter_baths_{baths}"] = baths
    for table, key in ((refs.HOME_TYPES, "home_type"), (refs.CONDITIONS, "condition"), (refs.FEATURES, "features"),
                       (refs.FLOORS, "floor"), (refs.ENERGY_RATINGS, "energy_rating"), (refs.OCCUPANCY, "occupancy")):
        for value in data.get(key) or []:
            name, token = table[value]
            query[name] = token
    if data.get("furnished"):
        name, token = refs.FURNISHED[data["furnished"]]
        query[name] = token
    if data.get("published"):
        query["adfilter_published"] = refs.PUBLISHED[data["published"]][operation]
    if data.get("sort"):
        site_value = refs.SORTS[data["sort"]].get(country)
        if site_value:
            query[refs.SORT_PARAM[country]] = site_value
    return query


def _pagination(parsed, page):
    """The scraper's pagination block from a parsed list page. The site
    prints the total in the h1 and caps every search at refs.MAX_PAGES."""
    total = parsed.get("total")
    if parsed.get("is_zero_results"):
        total = 0
    if total is None:
        return {"page": page, "items_per_page": ITEMS_PER_PAGE, "has_next": bool(parsed.get("has_next")),
                "total_pages": None, "total_count": None}
    total_pages = min(math.ceil(total / ITEMS_PER_PAGE), refs.MAX_PAGES)
    return {"page": page, "items_per_page": ITEMS_PER_PAGE, "total_pages": total_pages, "total_count": total}


def _echo(data, keys):
    return {key: data.get(key) for key in keys}


# ---- locations/search ---------------------------------------------------------------

def _locations_search(query, country, operation, property_type, language):
    payload = fetch_suggest(country, language, operation, _typology(property_type), query)
    results = parsers.parse_suggestions(payload, country)
    return {"query": query, "country": country, "count": len(results), "results": results}


def locations_search(**data):
    return cached_call("idealista.locations", data, _locations_search, ttl.LOCATIONS_CACHE)


def _resolve_place(country, language, operation, property_type, name):
    """A typed place name -> the first typeahead match (dict) or NotFound."""
    answer = locations_search(query=name, country=country, operation=operation,
                              property_type=property_type, language=language)
    for row in answer["results"]:
        if row.get("slug"):
            return row
    raise IdealistaNotFound(f"No idealista location matches '{name}'.")


# ---- properties/search ----------------------------------------------------------------

def _segment_meta(country, segment):
    """A listing path segment -> (operation, public property type)."""
    for (operation, typology), value in refs._LISTING_SEGMENT[country].items():
        if value == segment:
            return operation, parsers._public_type(typology)
    return None, None


def _properties_search(location, country, operation, property_type, page, language, **filters):
    kind, value = refs.classify_location(location)
    link_query = {}
    resolved = {"name": None, "slug": None, "id": None, "type": None}
    if kind == "link":
        country, path, link_query = value
        if f"/{refs.AREAS_SEGMENT[country]}/" in path and link_query.get("shape"):
            # a drawn-area link: the shape flow (the request's own filters apply)
            parts = path.strip("/").split("/")
            if len(parts) < 2:
                raise ValueError("Not an idealista drawn-area link (expected /areas/<segment>/?shape=…).")
            segment = parts[1]
            operation, property_type = _segment_meta(country, segment)
            if operation is None:
                raise ValueError("Not an idealista drawn-area link (expected /areas/<segment>/?shape=…).")
            shape = f"(({unquote(link_query['shape']).strip('()')}))"
            data = {**filters, "country": country, "operation": operation, "property_type": property_type or "homes",
                    "page": page, "language": language}
            result = _properties_shape(shape, **data)
            result["location"] = {"name": None, "slug": None, "id": None, "type": "drawn_area"}
            return result
        segment, slug, filter_segment, link_page = refs.split_listing_path(country, path)
        operation, property_type = _segment_meta(country, segment)
        if page == 1 and link_page > 1:
            page = link_page
        resolved["slug"] = slug
    else:
        # an impossible pair (rooms for sale, ...) is a 400 before any upstream call
        segment = refs.listing_segment(country, operation, _typology(property_type))
        if kind == "name":
            place = _resolve_place(country, language, operation, property_type, value)
            resolved = {"name": place.get("name"), "slug": place.get("slug"), "id": place.get("id"),
                        "type": place.get("type")}
            slug = place["slug"]
        else:
            slug = value
            resolved["slug"] = slug
        filter_segment = None
    query = {k: v for k, v in link_query.items() if k.startswith("adfilter_") or k in refs.SORT_PARAM.values()}
    query.update(_filter_params(filters, country, operation or "sale"))
    path = refs.listing_path(country, language, segment, slug, filter_segment, page)
    html, _status = fetch_listing_page(country, path, query or None)
    parsed = parsers.parse_listing(html, country, operation, property_type, page=page)
    return {
        "location": resolved,
        "country": country,
        "operation": operation,
        "property_type": property_type,
        "link": parsed["link"],
        "title": parsed["title"],
        "results": parsed["results"],
        "pagination": _pagination(parsed, page),
    }


def properties_search(**data):
    return cached_call("idealista.search", data, _properties_search, ttl.SEARCH_CACHE)


# ---- properties/shape -----------------------------------------------------------------

def _properties_shape(shape, country, operation, property_type, page, language, **filters):
    segment = refs.listing_segment(country, operation, _typology(property_type))
    query = {"shape": shape}
    query.update(_filter_params(filters, country, operation))
    path = refs.areas_path(country, language, segment, page)
    html, _status = fetch_listing_page(country, path, query)
    parsed = parsers.parse_listing(html, country, operation, property_type, page=page)
    return {
        "shape": {"points": refs.shape_points(shape), "encoded": shape},
        "country": country,
        "operation": operation,
        "property_type": property_type,
        "link": parsed["link"] or refs.absolute(country, path) + "?shape=" + shape,
        "title": parsed["title"],
        "results": parsed["results"],
        "pagination": _pagination(parsed, page),
    }


def properties_shape(**data):
    return cached_call("idealista.shape", data, _properties_shape, ttl.SEARCH_CACHE)


# ---- properties/details ---------------------------------------------------------------

def _property_details(property, country, language):
    html = fetch_detail(country, language, property)
    if parsers.is_not_found_page(html):
        raise IdealistaNotFound(f"listing {property} not found")
    try:
        record = parsers.parse_detail(html, country, property, language=language)
    except ValueError:
        raise IdealistaNotFound(f"listing {property} not found")
    if not record["photos"]:
        # the inline gallery is empty on a few layouts; the photo JSON is open
        try:
            media = parsers.parse_multimedia(fetch_multimedia(country, property), country)
        except Exception:
            media = None
        if media:
            record["photos"] = media["photos"]
            record["photos_count"] = len(media["photos"]) or None
            record["floor_plans"] = record["floor_plans"] or media["floor_plans"]
            record["home_staging"] = record["home_staging"] or media["home_staging"]
    record["country"] = country
    return record


def property_details(**data):
    return cached_call("idealista.details", data, _property_details, ttl.DETAILS_CACHE)


# ---- the agency microsite (shared page) --------------------------------------------------

def _agency_page(country, language, agency, segment=None, location=None, page=1):
    html, status = fetch_agency(country, language, agency, segment, location, page)
    if status == 404 and not (segment and is_zero_results(html)):
        raise IdealistaNotFound(f"agency {agency} not found")
    try:
        profile = parsers.parse_agency(html, country, agency)
    except ValueError:
        if status == 404:
            profile = None
        else:
            raise IdealistaNotFound(f"agency {agency} not found")
    operation, property_type = _segment_meta(country, segment) if segment else (None, None)
    listing = parsers.parse_listing(html, country, operation, property_type, page=page)
    if status == 404:
        # past the end the h1 still prints the listing's total; an empty
        # listing prints none
        total = parsers.parse_list_total(html)
        listing["results"], listing["total"], listing["has_next"] = [], total, False
        listing["is_zero_results"] = not total
    return {"profile": profile, "listing": listing}


def _agency_page_cached(country, language, agency, segment=None, location=None, page=1):
    return cached_call("idealista.agency_page",
                       {"country": country, "language": language, "agency": agency, "segment": segment,
                        "location": location, "page": page},
                       _agency_page, ttl.AGENCY_CACHE if not segment else ttl.AGENCY_LISTINGS_CACHE)


# ---- agencies/details -----------------------------------------------------------------

def agency_details(agency, country, language):
    page = _agency_page_cached(country, language, agency)
    profile = page["profile"] or {}
    return {**profile, "country": country}


# ---- agencies/properties ----------------------------------------------------------------

def _agency_properties(agency, country, operation, property_type, location, page, language, **filters):
    segment = refs.listing_segment(country, operation, _typology(property_type))
    query = _filter_params(filters, country, operation)
    if query:
        # a filtered listing is its own page (not the cached microsite)
        path = refs.agency_path(country, language, agency, segment, location, page)
        html, status = fetch_listing_page(country, path, query)
        if status == 404 and not is_zero_results(html):
            # the site's error page: a dead slug (an empty filtered listing
            # is a 404 that still carries the microsite + zero-results box)
            raise IdealistaNotFound(f"agency {agency} not found")
        listing = parsers.parse_listing(html, country, operation, property_type, page=page)
        profile = _agency_page_cached(country, language, agency)["profile"] or {}
    else:
        page_data = _agency_page_cached(country, language, agency, segment, location, page)
        listing, profile = page_data["listing"], page_data["profile"] or {}
    return {
        "agency": {"slug": agency, "name": profile.get("name"), "link": profile.get("link") or refs.agency_link(country, agency),
                   "properties_count": profile.get("properties_count")},
        "country": country,
        "operation": operation,
        "property_type": property_type,
        "location": location,
        "link": listing["link"],
        "title": listing["title"],
        "results": listing["results"],
        "pagination": _pagination(listing, page),
    }


def agency_properties(**data):
    return cached_call("idealista.agency_listings", data, _agency_properties, ttl.AGENCY_LISTINGS_CACHE)


# ---- agencies/search (the featured-agencies directory) ------------------------------------

def _directory_index(country, language):
    html = fetch_directory_index(country, language)
    return parsers.parse_directory_index(html, country)


def fetch_directory_index(country, language):
    head, _tail = refs.AGENCIES_DIRECTORY[country]
    from idealista import fetch as _fetch
    html, _status = _fetch._get_html(country, f"{refs.locale_prefix(country, language)}/{head}/", None,
                                     "agencies directory index")
    return html


def _directory_slug(country, language, location):
    """A directory slug, a directory link path, or a place name -> the slug."""
    location = location.strip()
    head, tail = refs.AGENCIES_DIRECTORY[country]
    if location.startswith("/"):                       # a link path from the schema
        parts = [p for p in location.strip("/").split("/") if p]
        if parts and parts[0] == head:
            parts = parts[1:]
        if parts and re.match(rf"^{refs.PAGE_SEGMENT[country]}-\d+(?:\.htm)?$", parts[-1]):
            parts = parts[:-1]                         # the directory has no paging
        if parts and parts[-1] == tail:
            parts = parts[:-1]
        if not parts:
            raise IdealistaNotFound("The link is not an agencies-directory page.")
        return "/".join(parts)
    kind, value = refs.classify_location(location)
    if kind == "slug":
        return value
    index = cached_call("idealista.directory_index", {"country": country, "language": language},
                        _directory_index, ttl.DIRECTORY_INDEX_CACHE)
    wanted = _fold(value)
    exact = [row for row in index if _fold(row["name"] or "") == wanted]
    partial = [row for row in index if wanted in _fold(row["name"] or "") or wanted in _fold(row["slug"])]
    for row in exact + partial:
        return row["slug"]
    raise IdealistaNotFound(f"No agencies directory matches '{value}' on idealista.{country}.")


def _fold(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower().replace("-", " ").strip()


def _agencies_search(location, country, language):
    slug = _directory_slug(country, language, location)
    html = fetch_directory(country, language, slug)
    parsed = parsers.parse_directory(html, country)
    return {
        "location": slug,
        "country": country,
        "title": parsed["title"],
        "count": len(parsed["results"]),
        "results": parsed["results"],
    }


def agencies_search(**data):
    return cached_call("idealista.agencies", data, _agencies_search, ttl.DIRECTORY_CACHE)
