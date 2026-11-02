"""Cache TTL per /idealista/* endpoint (cache.py, keyed on the validated
params). Listings move daily (new ads, price drops, withdrawals), so the
search views cache for hours, not days; a listing page's own facts change
only when the advertiser edits it; the location index and agency profiles
are near-static.
"""
from datetime import timedelta

# locations/search: the site's place index — new zones appear rarely; the
# listing counts in it are only a hint.
LOCATIONS_CACHE = timedelta(days=7)
# properties/search + properties/shape: one page of a search; the order and
# membership change through the day, prices too.
SEARCH_CACHE = timedelta(hours=6)
# properties/details: the advertiser edits price / text now and then; a
# withdrawn listing turns 404 — serve the last page for a day at most.
DETAILS_CACHE = timedelta(hours=24)
# agencies/details: the profile (address, languages, counts) is near-static.
AGENCY_CACHE = timedelta(days=3)
# agencies/properties: the agency's own listing, same cadence as a search.
AGENCY_LISTINGS_CACHE = timedelta(hours=6)
# agencies/search: the featured agencies of a location rotate slowly.
DIRECTORY_CACHE = timedelta(days=1)
# the directory index (which locations the directory lists) — static.
DIRECTORY_INDEX_CACHE = timedelta(days=30)
