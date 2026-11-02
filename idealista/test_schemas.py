"""Offline tests for the /idealista/* request schemas and the filter -> query
mapping.

    python -m pytest idealista/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from idealista import api, refs, schemas  # noqa: E402


def _errors(schema, data):
    with pytest.raises(ValidationError) as info:
        schema().load(data)
    return info.value.messages


# ---- locations/search ----------------------------------------------------------------

def test_locations_search_schema():
    loaded = schemas.LocationsSearchSchema().load({"query": " Madr "})
    assert loaded == {"query": "Madr", "country": "es", "operation": "sale", "property_type": "homes", "language": "en"}
    loaded = schemas.LocationsSearchSchema().load({"query": "Mila", "country": "IT", "operation": "Rent",
                                                  "property_type": "Rooms", "language": "fr"})
    assert loaded["country"] == "it" and loaded["operation"] == "rent" and loaded["property_type"] == "rooms"
    assert "query" in _errors(schemas.LocationsSearchSchema, {})
    assert "country" in _errors(schemas.LocationsSearchSchema, {"query": "x", "country": "pt"})
    assert "language" in _errors(schemas.LocationsSearchSchema, {"query": "x", "language": "es"})


# ---- properties/search ---------------------------------------------------------------

def test_properties_search_accepts_name_slug_and_link():
    for value in ("Madrid", "Chamberí, Madrid", "28013", "madrid-madrid", "madrid/chamberi",
                  "https://www.idealista.com/en/venta-viviendas/madrid-madrid/pagina-2.htm"):
        loaded = schemas.PropertiesSearchSchema().load({"location": value})
        assert loaded["location"] == value and loaded["page"] == 1


def test_properties_search_filters():
    loaded = schemas.PropertiesSearchSchema().load({
        "location": "Madrid", "operation": "rent", "min_price": "800", "max_price": "1500", "min_size": "50",
        "bedrooms": "2, 3", "bathrooms": "2", "home_type": "flat,penthouse", "condition": "good",
        "features": "lift, terrace,pets_allowed", "furnished": "furnished", "floor": "top", "energy_rating": "high,medium",
        "published": "last_week", "sort": "newest", "page": "3"})
    assert loaded["bedrooms"] == ["2", "3"] and loaded["bathrooms"] == ["2"]
    assert loaded["home_type"] == ["flat", "penthouse"] and loaded["features"] == ["lift", "terrace", "pets_allowed"]
    assert loaded["min_price"] == 800 and loaded["max_price"] == 1500 and loaded["page"] == 3
    query = api._filter_params(loaded, "es", "rent")
    assert query == {
        "adfilter_pricemin": "800", "adfilter_price": "1500", "adfilter_area": "50",
        "adfilter_rooms_2": "2", "adfilter_rooms_3": "3", "adfilter_baths_2": "2",
        "adfilter_onlyflats": "1", "adfilter_penthouse": "1", "adfilter_goodcondition": "3",
        "adfilter_lift": "1", "adfilter_hasterrace": "1", "adfilter_housingpetsallowed": "1",
        "adfilter_amenity": "3", "adfilter_top_floor": "1",
        "adfilter_energyCertificateHigh": "1", "adfilter_energyCertificateMedium": "1",
        "adfilter_published": "2", "ordenado-por": "fecha-publicacion-desc"}


def test_filter_params_market_differences():
    loaded = schemas.PropertiesSearchSchema().load({"location": "Milano", "country": "it", "bedrooms": "4",
                                                    "published": "last_48_hours", "sort": "price_drop"})
    query = api._filter_params(loaded, "it", "sale")
    assert query["adfilter_rooms_4_more"] == "4" and query["adfilter_rooms_4"] == "4" and query["adfilter_rooms_5_more"] == "5"
    assert query["adfilter_published"] == "1" and query["ordine"] == "queda-desc"
    assert api._filter_params(schemas.PropertiesSearchSchema().load({"location": "x", "published": "last_48_hours"}),
                              "es", "rent")["adfilter_published"] == "4"
    assert api._filter_params(schemas.PropertiesSearchSchema().load({"location": "x"}), "es", "sale") == {}


@pytest.mark.parametrize("data,field", [
    ({}, "location"),
    ({"location": ""}, "location"),
    ({"location": "https://www.idealista.pt/comprar-casas/lisboa/"}, "location"),
    ({"location": "https://example.com/venta-viviendas/madrid-madrid/"}, "location"),
    ({"location": "Madrid", "min_price": "500", "max_price": "100"}, "max_price"),
    ({"location": "Madrid", "min_size": "90", "max_size": "80"}, "max_size"),
    ({"location": "Madrid", "bedrooms": "5"}, "bedrooms"),
    ({"location": "Madrid", "bathrooms": "0"}, "bathrooms"),
    ({"location": "Madrid", "features": "jacuzzi"}, "features"),
    ({"location": "Madrid", "home_type": "castle"}, "home_type"),
    ({"location": "Madrid", "sort": "cheapest"}, "sort"),
    ({"location": "Madrid", "sort": "price_per_m2_asc", "country": "it"}, "sort"),
    ({"location": "Madrid", "published": "today"}, "published"),
    ({"location": "Madrid", "page": "61"}, "page"),
    ({"location": "Madrid", "page": "0"}, "page"),
    ({"location": "Madrid", "operation": "buy"}, "operation"),
    ({"location": "Madrid", "property_type": "castles"}, "property_type"),
    ({"location": "Madrid", "url": "x"}, "url"),
    ({"location": "Madrid", "id": "1"}, "id"),
])
def test_properties_search_rejects(data, field):
    assert field in _errors(schemas.PropertiesSearchSchema, data)


# ---- properties/shape ----------------------------------------------------------------

def test_properties_shape_schema():
    loaded = schemas.PropertiesShapeSchema().load({"shape": "40.44493,-3.67268;40.45127,-3.65412;40.43897,-3.63954"})
    assert loaded["shape"].startswith("((") and loaded["shape"].endswith("))")
    loaded = schemas.PropertiesShapeSchema().load(
        {"shape": "https://www.idealista.com/en/areas/venta-viviendas/?shape=%28%28ykzuFfilUsf%40_sBzkAczAfz%40rcB%29%29",
         "operation": "rent", "max_price": "1500"})
    assert loaded["shape"] == "((ykzuFfilUsf@_sBzkAczAfz@rcB))" and loaded["operation"] == "rent"
    for bad in ({}, {"shape": "40,-3"}, {"shape": "a;b;c"}, {"shape": "https://www.idealista.com/en/venta-viviendas/madrid-madrid/"}):
        assert "shape" in _errors(schemas.PropertiesShapeSchema, bad)


# ---- properties/details --------------------------------------------------------------

def test_property_details_schema():
    assert schemas.PropertyDetailsSchema().load({"property": "109630900"}) == \
        {"property": "109630900", "country": "es", "language": "en"}
    loaded = schemas.PropertyDetailsSchema().load({"property": "https://www.idealista.it/en/immobile/37305588/"})
    assert loaded == {"property": "37305588", "country": "it", "language": "en"}
    loaded = schemas.PropertyDetailsSchema().load({"property": "https://www.idealista.com/inmueble/109630900/", "country": "it"})
    assert loaded["country"] == "es"          # the link wins over the param
    loaded = schemas.PropertyDetailsSchema().load({"property": "37305588", "country": "it", "language": "de"})
    assert loaded["country"] == "it" and loaded["language"] == "de"
    for bad in ({}, {"property": "abc"}, {"property": "https://www.idealista.pt/imovel/1/"},
                {"property": "https://www.idealista.com/pro/x/"}, {"property": "1", "id": "1"}):
        errors = _errors(schemas.PropertyDetailsSchema, bad)
        assert "property" in errors or "id" in errors


# ---- agencies ------------------------------------------------------------------------

def test_agency_details_schema():
    assert schemas.AgencyDetailsSchema().load({"agency": "WalterHausChamberi"}) == \
        {"agency": "walterhauschamberi", "country": "es", "language": "en"}
    loaded = schemas.AgencyDetailsSchema().load({"agency": "https://www.idealista.it/en/pro/fast-house-milano-case-immobiliare/"})
    assert loaded["agency"] == "fast-house-milano-case-immobiliare" and loaded["country"] == "it"
    for bad in ({}, {"agency": "a b"}, {"agency": "https://www.idealista.com/inmueble/1/"}, {"agency": "x", "slug": "x"}):
        assert _errors(schemas.AgencyDetailsSchema, bad)


def test_agency_properties_schema():
    loaded = schemas.AgencyPropertiesSchema().load({"agency": "clikalia", "operation": "sale", "location": "madrid-madrid",
                                                    "page": "2", "max_price": "400000"})
    assert loaded["agency"] == "clikalia" and loaded["location"] == "madrid-madrid" and loaded["page"] == 2
    assert loaded["max_price"] == 400000 and loaded["property_type"] == "homes"
    loaded = schemas.AgencyPropertiesSchema().load({"agency": "https://www.idealista.com/pro/clikalia/venta-viviendas/"})
    assert loaded["location"] is None
    assert "location" in _errors(schemas.AgencyPropertiesSchema, {"agency": "clikalia", "location": "Madrid city"})
    assert "agency" in _errors(schemas.AgencyPropertiesSchema, {})


def test_agencies_search_schema():
    assert schemas.AgenciesSearchSchema().load({"location": "Alicante"}) == \
        {"location": "Alicante", "country": "es", "language": "en"}
    loaded = schemas.AgenciesSearchSchema().load({"location": "balears-illes/mallorca"})
    assert loaded["location"] == "balears-illes/mallorca"
    loaded = schemas.AgenciesSearchSchema().load(
        {"location": "https://www.idealista.it/en/agenzie-immobiliari/milano-milano/agenzie-immobiliari"})
    assert loaded == {"location": "/agenzie-immobiliari/milano-milano/agenzie-immobiliari", "country": "it", "language": "en"}
    assert "location" in _errors(schemas.AgenciesSearchSchema, {})
    assert "location" in _errors(schemas.AgenciesSearchSchema, {"location": "https://www.idealista.pt/x/"})


def test_directory_slug_resolution():
    assert api._directory_slug("es", "en", "madrid-provincia") == "madrid-provincia"
    assert api._directory_slug("es", "en", "/agencias-inmobiliarias/alicante/inmobiliarias") == "alicante"
    assert api._directory_slug("it", "en", "/en/agenzie-immobiliari/milano-milano/agenzie-immobiliari".replace("/en", "", 1)) == "milano-milano"
    assert api._directory_slug("es", "en", "/agencias-inmobiliarias/alicante/inmobiliarias/pagina-2.htm") == "alicante"
    assert api._fold("Málaga-Provincia") == "malaga provincia"


def test_filter_vocabularies_match_the_tables():
    assert set(refs.HOME_TYPES) == {"flat", "penthouse", "duplex", "house", "detached", "semi_detached", "terraced",
                                    "country_house", "apartment", "villa", "loft", "single_storey", "attic"}
    assert all(len(v) == 2 for v in refs.FEATURES.values())
    assert refs.SORTS["price_per_m2_asc"].get("it") is None
    assert refs.PUBLISHED["last_48_hours"] == {"sale": "1", "rent": "4"}
