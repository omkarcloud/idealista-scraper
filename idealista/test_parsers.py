"""Offline tests for the idealista parsers, reference resolvers and value
helpers.

    python -m pytest idealista/test_parsers.py -q

Fixtures are real www.idealista.com / www.idealista.it pages captured
2026-10-30 (idealista/fixtures/), rendered under /en/: list pages (sale,
rent, rooms, new developments, offices, a drawn area, a zero-result page,
page 61 past the cap, Milan), detail pages (private rental, professional
sale, new-development unit, room, office, Milan, a dead id), agency
microsites (+ a listing page, a past-the-end page, a dead slug), the
agencies directories and indexes, three typeahead answers, one photo JSON
and a DataDome block page. No network.
"""
import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from idealista import parsers as P, refs  # noqa: E402
from idealista import fetch as F  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


@pytest.fixture(scope="module")
def madrid():
    return P.parse_listing(fixture("list_sale_madrid.html"), "es", "sale", "homes", page=1)


@pytest.fixture(scope="module")
def pro_detail():
    return P.parse_detail(fixture("detail_professional_sale_109630900.html"), "es", language="en",
                          today=date(2026, 10, 31))


@pytest.fixture(scope="module")
def private_detail():
    return P.parse_detail(fixture("detail_private_rent_99199254.html"), "es", language="en",
                          today=date(2026, 10, 31))


# ---- refs -------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("109630900", "109630900"),
    (" 99199254 ", "99199254"),
    ("https://www.idealista.com/inmueble/109630900/", "109630900"),
    ("https://www.idealista.com/en/inmueble/109630900/?x=1", "109630900"),
    ("www.idealista.it/immobile/37305588/", "37305588"),
    ("//www.idealista.it/en/immobile/37305588", "37305588"),
])
def test_resolve_property(value, expected):
    assert refs.resolve_property(value) == expected


@pytest.mark.parametrize("value", [
    "", "abc", "12", "https://example.com/inmueble/109630900/",
    "https://www.idealista.com/pro/walterhauschamberi/",
    "https://www.idealista.pt/imovel/33939171/",
])
def test_resolve_property_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_property(value)


def test_property_country_follows_the_link():
    assert refs.property_country("https://www.idealista.it/immobile/37305588/") == "it"
    assert refs.property_country("https://www.idealista.com/inmueble/1/", "it") == "es"
    assert refs.property_country("109630900", "it") == "it"
    assert refs.property_country("109630900") == "es"


@pytest.mark.parametrize("value,expected", [
    ("walterhauschamberi", "walterhauschamberi"),
    ("Engel-Volkers-Barcelona", "engel-volkers-barcelona"),
    ("https://www.idealista.com/en/pro/walterhauschamberi/", "walterhauschamberi"),
    ("https://www.idealista.com/pro/clikalia/venta-viviendas/pagina-2.htm", "clikalia"),
    ("https://www.idealista.it/en/pro/fast-house-milano-case-immobiliare/affitto-case/", "fast-house-milano-case-immobiliare"),
])
def test_resolve_agency(value, expected):
    assert refs.resolve_agency(value) == expected


@pytest.mark.parametrize("value", ["", "a b", "https://www.idealista.com/inmueble/1/", "https://example.com/pro/x/"])
def test_resolve_agency_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_agency(value)


@pytest.mark.parametrize("value,kind", [
    ("Madrid", "name"), ("Chamberí, Madrid", "name"), ("28013", "name"), ("madrid-madrid", "slug"),
    ("madrid/chamberi", "slug"), ("/barcelona/ciutat-vella/la-barceloneta/", "slug"),
    ("https://www.idealista.com/en/venta-viviendas/madrid-madrid/", "link"),
])
def test_classify_location(value, kind):
    assert refs.classify_location(value)[0] == kind


def test_classify_location_rejects():
    with pytest.raises(ValueError):
        refs.classify_location("")
    with pytest.raises(ValueError):
        refs.classify_location("https://www.idealista.pt/comprar-casas/lisboa/")


def test_split_listing_path():
    assert refs.split_listing_path("es", "/venta-viviendas/madrid-madrid/") == ("venta-viviendas", "madrid-madrid", None, 1)
    assert refs.split_listing_path("es", "/alquiler-viviendas/madrid/chamberi/con-ascensor,terraza/pagina-3.htm") == \
        ("alquiler-viviendas", "madrid/chamberi", "con-ascensor,terraza", 3)
    assert refs.split_listing_path("es", "/geo/venta-viviendas/codigo-postal-28013/pagina-2.htm") == \
        ("venta-viviendas", "geo/codigo-postal-28013", None, 2)
    assert refs.split_listing_path("it", "/vendita-case/milano-milano/lista-2.htm") == ("vendita-case", "milano-milano", None, 2)
    # the map view of a search is the same search
    assert refs.split_listing_path("es", "/venta-viviendas/madrid-madrid/mapa-google") == ("venta-viviendas", "madrid-madrid", None, 1)
    assert refs.split_listing_path("it", "/vendita-case/milano-milano/lista-mappa") == ("vendita-case", "milano-milano", None, 1)
    with pytest.raises(ValueError):
        refs.split_listing_path("es", "/inmueble/109630900/")
    with pytest.raises(ValueError):
        refs.split_listing_path("es", "/")


def test_paths():
    assert refs.listing_path("es", "en", "venta-viviendas", "madrid-madrid") == "/en/venta-viviendas/madrid-madrid/"
    assert refs.listing_path("es", "en", "venta-viviendas", "madrid-madrid", "con-ascensor", 2) == \
        "/en/venta-viviendas/madrid-madrid/con-ascensor/pagina-2.htm"
    assert refs.listing_path("es", "fr", "alquiler-viviendas", "geo/codigo-postal-28013", None, 2) == \
        "/fr/geo/alquiler-viviendas/codigo-postal-28013/pagina-2.htm"
    assert refs.listing_path("it", "it", "vendita-case", "milano-milano", None, 3) == "/vendita-case/milano-milano/lista-3.htm"
    assert refs.areas_path("es", "en", "venta-viviendas", 2) == "/en/areas/venta-viviendas/pagina-2"
    assert refs.areas_path("it", "en", "vendita-case") == "/en/aree/vendita-case/"
    assert refs.detail_path("es", "en", "1") == "/en/inmueble/1/"
    assert refs.detail_path("it", "it", "1") == "/immobile/1/"
    assert refs.agency_path("es", "en", "clikalia") == "/en/pro/clikalia/"
    assert refs.agency_path("es", "en", "clikalia", "venta-viviendas", "madrid-madrid", 2) == \
        "/en/pro/clikalia/venta-viviendas/madrid-madrid/pagina-2.htm"
    assert refs.directory_path("es", "en", "alicante") == "/en/agencias-inmobiliarias/alicante/inmobiliarias"
    assert refs.directory_path("it", "en", "milano-milano") == "/en/agenzie-immobiliari/milano-milano/agenzie-immobiliari"
    assert refs.suggest_path("es", "en", "sale", "home", "Madr") == "/en/locationsSuggest/sale/home/Madr"
    assert refs.property_link("es", "5") == "https://www.idealista.com/inmueble/5/"
    assert refs.agency_link("it", "x") == "https://www.idealista.it/pro/x/"


def test_listing_segment_rejects_impossible_pairs():
    assert refs.listing_segment("es", "rent", "room") == "alquiler-habitacion"
    with pytest.raises(ValueError):
        refs.listing_segment("es", "sale", "room")
    with pytest.raises(ValueError):
        refs.listing_segment("it", "rent", "transfer")


def test_polyline_round_trip():
    points = [(40.44493, -3.67268), (40.45127, -3.65412), (40.43897, -3.63954), (40.42949, -3.65564)]
    assert refs.encode_polyline(points) == "ykzuFfilUsf@_sBzkAczAfz@rcB"
    assert refs.decode_polyline("ykzuFfilUsf@_sBzkAczAfz@rcB") == points


def test_resolve_shape():
    shape = refs.resolve_shape("40.44493,-3.67268;40.45127,-3.65412;40.43897,-3.63954;40.42949,-3.65564")
    assert shape == "((ykzuFfilUsf@_sBzkAczAfz@rcB))"
    assert refs.resolve_shape("40.44493,-3.67268 40.45127,-3.65412 40.43897,-3.63954") .startswith("((")
    assert refs.resolve_shape(
        "https://www.idealista.com/en/areas/venta-viviendas/?shape=%28%28ykzuFfilUsf%40_sBzkAczAfz%40rcB%29%29") == shape
    assert refs.shape_points(shape)[0] == {"latitude": 40.44493, "longitude": -3.67268}
    for bad in ("", "40,-3", "40.4,-3.6;40.5,-3.6", "a,b;c,d;e,f", "95,0;0,0;1,1",
                "https://www.idealista.com/en/venta-viviendas/madrid-madrid/"):
        with pytest.raises(ValueError):
            refs.resolve_shape(bad)


# ---- value helpers ---------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2,495,000 €", 2495000), ("2.495.000", 2495000), ("1 114", 1114), ("8,724 €/m²", 8724), ("", None), (None, None), ("abc", None),
])
def test_parse_int(value, expected):
    assert P.parse_int(value) == expected


def test_parse_decimal():
    assert P.parse_decimal("153,1 kWh/m² year") == 153.1
    assert P.parse_decimal("26 kWh") == 26.0
    assert P.parse_decimal("-") is None


def test_parse_price():
    assert P.parse_price("2,495,000 €") == {"amount": 2495000, "currency": "EUR", "period": None, "text": "2,495,000 €"}
    assert P.parse_price("1,114 €/month")["period"] == "month"
    assert P.parse_price("620€/mese")["period"] == "month"
    assert P.parse_price("€385/month") == {"amount": 385, "currency": "EUR", "period": "month", "text": "€385/month"}
    assert P.parse_price("Price on request") is None
    assert P.parse_price("") is None


def test_parse_update_date():
    assert P.parse_update_date("Listing updated on 30 October", today=date(2026, 10, 31)) == "2026-10-30"
    assert P.parse_update_date("Listing updated on 30 October", today=date(2026, 10, 1)) == "2025-10-30"
    assert P.parse_update_date("Anuncio actualizado el 3 de enero", today=date(2026, 10, 31)) == "2026-01-03"
    assert P.parse_update_date("", today=date(2026, 10, 31)) is None
    assert P.parse_update_date("updated yesterday", today=date(2026, 10, 31)) is None
    assert P.parse_update_date("Annonce mise à jour le 3 juillet", today=date(2026, 10, 31)) == "2026-07-03"
    assert P.parse_update_date("Annonce mise à jour le 3 juin", today=date(2026, 10, 31)) == "2026-06-03"
    assert P.parse_update_date("Anzeige aktualisiert am 30. Oktober", today=date(2026, 10, 31)) == "2026-10-30"


# ---- list pages -------------------------------------------------------------------------

def test_listing_page(madrid):
    assert madrid["total"] == 19831
    assert madrid["page"] == 1 and madrid["has_next"] is True
    assert madrid["link"] == "https://www.idealista.com/en/venta-viviendas/madrid-madrid/"
    assert madrid["title"].startswith("Property for sale in Madrid")
    assert len(madrid["results"]) == 30
    assert madrid["is_zero_results"] is False


def test_listing_card(madrid):
    card = madrid["results"][0]
    assert card["id"] == "109630900"
    assert card["link"] == "https://www.idealista.com/inmueble/109630900/"
    assert card["title"] == "Flat / apartment in Goya, Madrid"
    assert card["operation"] == "sale" and card["property_type"] == "homes"
    assert card["price"] == {"amount": 2495000, "currency": "EUR", "period": None, "text": "2,495,000 €"}
    assert card["price_per_m2"] == 8724
    assert card["rooms"] == 4 and card["size_m2"] == 286
    assert card["floor"] == {"text": "2nd floor exterior with lift", "is_exterior": True, "has_lift": True}
    assert card["details"] == ["4 bed.", "286 m²", "2nd floor exterior with lift"]
    assert card["tags"] == ["Luxury"]
    assert card["photos_count"] == 59
    assert card["thumbnail"].startswith("https://img4.idealista.com/")
    assert card["has_floor_plan"] and card["has_video"] and card["has_3d_tour"] and card["has_home_staging"]
    assert card["is_professional"] is True and card["is_highlighted"] is True
    assert card["agency"] == {"name": "Walter Haus Madrid", "slug": "walterhauschamberi",
                              "link": "https://www.idealista.com/pro/walterhauschamberi/",
                              "logo": "https://st3.idealista.com/ff/20/20/walterhauschamberi.gif"}
    assert card["description"].startswith("Walter Haus Real Estate")


def test_listing_card_parking_and_ribbons(madrid):
    with_parking = [c for c in madrid["results"] if c["parking"]]
    assert with_parking and with_parking[0]["parking"] in ("included", "optional")
    ribbons = [c for c in madrid["results"] if c["ribbons"]]
    assert ribbons and ribbons[0]["ribbons"][0] in ("New homes", "Finished new development")


def test_rent_and_room_cards():
    rent = P.parse_listing(fixture("list_rent_madrid.html"), "es", "rent", "homes")
    assert rent["total"] == 8045
    assert all(c["price"]["period"] == "month" for c in rent["results"] if c["price"])
    rooms = P.parse_listing(fixture("list_rooms_madrid.html"), "es", "rent", "rooms")
    card = rooms["results"][0]
    assert card["id"] == "112942826" and card["price"]["amount"] == 620
    assert card["has_online_booking"] is True and "Online Booking" in card["ribbons"]
    assert card["listed_ago"] == "20 hours" and card["is_new_listing"] is True
    assert "Smoking is not allowed" in card["details"]


def test_office_and_new_development_cards():
    offices = P.parse_listing(fixture("list_offices_madrid.html"), "es", "sale", "offices")
    card = offices["results"][0]
    assert card["size_m2"] == 657 and card["price_per_m2"] == 1202 and card["rooms"] is None
    newdev = P.parse_listing(fixture("list_new_developments_madrid.html"), "es", "sale", "homes")
    assert newdev["total"] == 1196
    assert newdev["results"][0]["agency"]["slug"] == "clikalia"


def test_zero_results_page_is_empty_not_error():
    page = P.parse_listing(fixture("list_zero_results.html"), "es", "sale", "homes")
    assert page["results"] == [] and page["total"] is None and page["is_zero_results"] is True
    assert page["has_next"] is False
    assert F.is_zero_results(fixture("list_zero_results.html"))


def test_past_the_cap_page_is_empty():
    page = P.parse_listing(fixture("list_past_cap_page61.html"), "es", "sale", "homes", page=61)
    assert page["results"] == [] and page["has_next"] is False
    assert page["page"] == 1      # the site rendered page 1 again


def test_shape_and_italian_pages():
    shape = P.parse_listing(fixture("list_shape_madrid.html"), "es", "sale", "homes")
    assert shape["total"] == 601 and len(shape["results"]) == 30 and shape["has_next"]
    milan = P.parse_listing(fixture("list_sale_milano_it.html"), "it", "sale", "homes")
    assert milan["total"] == 15877
    card = milan["results"][0]
    assert card["link"] == "https://www.idealista.it/immobile/37305588/"
    assert card["rooms"] == 4 and card["size_m2"] == 162 and card["parking"] == "included"
    assert card["agency"]["link"] == "https://www.idealista.it/pro/fast-house-milano-case-immobiliare/"


def test_parse_list_total_shapes():
    assert P.parse_list_total("<h1 id='h1-container__text'>Property for sale, 28013, Madrid, Spain: 294 houses and flats</h1>") == 294
    assert P.parse_list_total("<h1><span id='h1-container__text'>17,375 flats / apartments for sale in Madrid</span></h1>") == 17375
    assert P.parse_list_total("<h1>Engel &amp; Völkers Barcelona: 4,016 houses and flats for sale</h1>") == 4016
    assert P.parse_list_total("<html></html>") is None


def test_parse_listing_on_junk():
    page = P.parse_listing("<html><body>nothing</body></html>", "es", "sale", "homes")
    assert page["results"] == [] and page["total"] is None and page["has_next"] is False
    assert P.parse_listing("", "es")["results"] == []


# ---- detail pages ----------------------------------------------------------------------

def test_detail_identity(pro_detail):
    assert pro_detail["id"] == "109630900"
    assert pro_detail["link"] == "https://www.idealista.com/inmueble/109630900/"
    assert pro_detail["title"] == "Flat / apartment for sale in Goya"
    assert pro_detail["subtitle"] == "Barrio de Salamanca, Madrid"
    assert pro_detail["operation"] == "sale" and pro_detail["property_type"] == "homes"
    assert pro_detail["price"] == {"amount": 2495000, "currency": "EUR", "period": None, "text": "2,495,000 €"}
    assert pro_detail["price_per_m2"] == 8724
    assert pro_detail["community_costs"] == {"amount": 385, "currency": "EUR", "period": "month", "text": "€385/month"}
    assert pro_detail["reference"] == "M11515V"
    assert pro_detail["updated_text"] == "Listing updated on 30 October"
    assert pro_detail["updated_date"] == "2026-10-30"
    assert pro_detail["tags"] == ["Luxury"]


def test_detail_facts(pro_detail):
    assert pro_detail["size_m2"] == 286 and pro_detail["rooms"] == 4 and pro_detail["bathrooms"] == 5
    assert pro_detail["floor"] == "2nd floor exterior" and pro_detail["is_exterior"] is True and pro_detail["has_lift"] is True
    assert pro_detail["condition"] == "good" and pro_detail["year_built"] == 1953
    assert pro_detail["orientation"] == "West"
    assert pro_detail["heating"] == "Individual heating: Natural gas"
    assert pro_detail["has_air_conditioning"] is True and pro_detail["has_wardrobes"] is True
    assert pro_detail["is_accessible"] is True
    assert pro_detail["is_new_development"] is False and pro_detail["is_offmarket"] is False
    titles = [s["title"] for s in pro_detail["features"]]
    assert titles == ["Basic features", "Building", "Amenities", "Energy performance certificate"]
    assert "286 m² built" in pro_detail["features"][0]["items"]


def test_detail_energy(pro_detail):
    assert pro_detail["energy_certificate"] == {
        "rating": "E", "consumption_rating": "E", "consumption_kwh_m2_year": 153.1,
        "emissions_rating": "E", "emissions_kg_co2_m2_year": 31.6, "is_exempt": False, "is_in_process": False}


def test_detail_location(pro_detail):
    loc = pro_detail["location"]
    assert loc["latitude"] == 40.4286597 and loc["longitude"] == -3.6684099
    assert loc["area"] == "Goya" and loc["district"] == "Barrio de Salamanca" and loc["city"] == "Madrid"
    assert loc["address"] is None          # the agency hides the street
    assert loc["location_id"] == "0-EU-ES-28"


def test_detail_media(pro_detail):
    assert pro_detail["photos_count"] == 59 and len(pro_detail["photos"]) == 59
    first = pro_detail["photos"][0]
    assert first["link"].startswith("https://img4.idealista.com/blur/WEB_DETAIL/")
    assert first["tag"] == "Living room" and first["width"] == 1500 and first["height"] == 999
    assert len(pro_detail["floor_plans"]) == 2
    assert pro_detail["videos"][0]["link"].endswith(".mp4") and pro_detail["videos"][0]["hd_link"].endswith(".mp4")
    assert pro_detail["tours_3d"] == ["https://my.matterport.com/show/?m=E31QiDrBDTR"]
    assert pro_detail["home_staging"]


def test_detail_advertiser(pro_detail, private_detail):
    assert pro_detail["advertiser"]["type"] == "professional"
    assert pro_detail["advertiser"]["agency"] == {
        "name": "Walter Haus Madrid", "slug": "walterhauschamberi",
        "link": "https://www.idealista.com/pro/walterhauschamberi/",
        "logo": "https://st3.idealista.com/ff/20/20/walterhauschamberi.gif"}
    assert private_detail["advertiser"] == {"type": "private", "name": "Pablo", "is_verified": False, "agency": None}


def test_private_rental_detail(private_detail):
    assert private_detail["price"] == {"amount": 1114, "currency": "EUR", "period": "month", "text": "1,114 €/month"}
    assert private_detail["price_per_m2"] == 3094
    assert private_detail["size_m2"] == 36 and private_detail["rooms"] == 2 and private_detail["bathrooms"] == 1
    assert private_detail["has_lift"] is False and private_detail["is_furnished"] is True
    assert private_detail["has_balcony"] is True
    assert private_detail["location"]["address"] == "Calle de la Mestrança, 49"
    assert private_detail["location"]["latitude"] == 41.3772954
    assert private_detail["energy_certificate"]["is_exempt"] is True
    assert private_detail["description"]["is_translated"] is False
    assert private_detail["description"]["text"].startswith("Second floor without elevator")


def test_room_detail():
    room = P.parse_detail(fixture("detail_room_112942826.html"), "es")
    assert room["property_type"] == "rooms" and room["operation"] == "rent"
    assert room["price"]["amount"] == 620 and room["has_online_booking"] is True
    assert room["rooms"] == 6 and room["bathrooms"] == 2 and room["size_m2"] == 117
    assert room["is_furnished"] is True
    assert room["description"] == {"text": room["description"]["text"], "language": "en", "is_translated": True,
                                   "original_language": "es"}
    assert room["advertiser"] == {"type": "professional", "name": "De Haro Space", "is_verified": True, "agency": None}
    assert [s["title"] for s in room["features"]][:2] == ["Looking for...", "Documents you must provide"]
    assert room["energy_certificate"] is None


def test_new_development_unit_detail():
    unit = P.parse_detail(fixture("detail_new_development_unit_112541619.html"), "es")
    assert unit["is_new_development"] is True and unit["condition"] == "new_build"
    assert unit["rooms"] == 0 and unit["bathrooms"] == 1 and unit["size_m2"] == 48
    assert unit["parking"] == "included" and unit["has_swimming_pool"] is True and unit["has_terrace"] is True
    assert unit["energy_certificate"]["rating"] == "A" and unit["energy_certificate"]["consumption_kwh_m2_year"] == 26.0
    assert unit["advertiser"]["agency"]["slug"] == "clikalia"


def test_office_detail():
    office = P.parse_detail(fixture("detail_office_112893152.html"), "es")
    assert office["property_type"] == "offices" and office["size_m2"] == 657 and office["price_per_m2"] == 1202
    assert office["rooms"] is None and office["is_furnished"] is None
    assert office["heating"] == "Heating"
    assert [s["title"] for s in office["features"]] == ["Basic features", "Building", "Amenities", "Security",
                                                        "Energy performance certificate"]
    assert office["energy_certificate"]["is_exempt"] is True
    assert office["tours_3d"] == ["https://my.matterport.com/show/?m=QHMjoRSrJEV"]


def test_italian_detail():
    milan = P.parse_detail(fixture("detail_it_37305588.html"), "it")
    assert milan["link"] == "https://www.idealista.it/immobile/37305588/"
    assert milan["price"]["amount"] == 1050000 and milan["community_costs"]["amount"] == 350
    assert milan["year_built"] == 1996 and milan["orientation"] == "North, South, East, West"
    assert milan["location"]["latitude"] == 45.44682 and milan["location"]["city"] == "Milan"
    assert milan["tags"] == ["Rented", "Bright"]
    assert milan["advertiser"]["agency"]["link"] == "https://www.idealista.it/pro/fast-house-milano-case-immobiliare/"


def test_detail_not_found_page():
    assert P.is_not_found_page(fixture("detail_not_found.html")) is True
    assert P.is_not_found_page(fixture("detail_professional_sale_109630900.html")) is False
    with pytest.raises(ValueError):
        P.parse_detail(fixture("detail_not_found.html"), "es")
    with pytest.raises(ValueError):
        P.parse_detail("<html><body>x</body></html>", "es")


def test_parse_config_and_js_arrays():
    cfg = P.parse_config(fixture("detail_professional_sale_109630900.html"))
    assert cfg["adId"] == 109630900 and cfg["buyingPrice"] == 2495000.0
    assert cfg["adCommercialName"] == "Walter Haus Madrid" and cfg["isOffmarket"] is False
    assert P.parse_config("") == {}
    assert P._js_array('var x = {videos: [{"src":"a"}, {src:"b",n:1}]}', "videos") == [{"src": "a"}, {"src": "b", "n": 1}]
    assert P._js_array("nothing", "videos") == []


def test_parse_multimedia():
    media = P.parse_multimedia(fixture("multimedia_109630900.json"))
    assert len(media["photos"]) == 59 and len(media["floor_plans"]) == 2 and len(media["videos"]) == 1
    assert media["photos"][0] == {"id": 1424442588, "tag": "Salón",
                                  "link": "https://img4.idealista.com/blur/591_420_mq/0/id.pro.es.image.master/b3/08/ae/1424442588.jpg"}
    assert P.parse_multimedia({}) == {"photos": [], "floor_plans": [], "videos": [], "tours_3d": [], "home_staging": []}


# ---- agencies --------------------------------------------------------------------------

def test_agency_profile():
    agency = P.parse_agency(fixture("agency_engel_volkers_barcelona.html"), "es", "engel-volkers-barcelona")
    assert agency["name"] == "Engel & Völkers Barcelona"
    assert agency["link"] == "https://www.idealista.com/pro/engel-volkers-barcelona/"
    assert agency["properties_count"] == 6655 and agency["since_year"] == 2014
    assert agency["publication_quality_percent"] == 67
    assert agency["address"] == "Avinguda Diagonal 640, Barcelona, 08017"
    assert agency["languages"][:3] == ["Español", "Català", "English"]
    assert agency["image"] == "https://st3.idealista.com/7c/a8/a4/main-engel-volkers-barcelona.jpg"
    assert agency["video"].endswith(".mp4")
    assert agency["registrations"] == ["AICAT - Registro oficial de agentes de Catalunya"]
    assert len(agency["locations"]) == 27 and agency["locations"][0]["id"] == "0-EU-ES-02"
    assert agency["default_listing_link"] == "https://www.idealista.com/pro/engel-volkers-barcelona/venta-viviendas/"
    assert agency["total_listing_pages"] == 134
    listing = P.parse_listing(fixture("agency_engel_volkers_barcelona.html"), "es", "sale", "homes")
    assert listing["total"] == 4016 and len(listing["results"]) == 30


def test_agency_listing_pages():
    page2 = P.parse_listing(fixture("agency_listings_page2.html"), "es", "sale", "homes", page=2)
    assert page2["page"] == 2 and len(page2["results"]) == 30 and page2["has_next"]
    past = P.parse_listing(fixture("agency_listings_past_end.html"), "es", "rent", "homes", page=999)
    assert past["results"] == [] and past["has_next"] is False


def test_agency_clikalia_and_italian():
    clikalia = P.parse_agency(fixture("agency_clikalia.html"), "es", "clikalia")
    assert clikalia["properties_count"] == 550 and clikalia["since_year"] == 2017
    assert clikalia["address"] == "Maria de Molina 39, Madrid, 28006"
    milan = P.parse_agency(fixture("agency_it_fast_house.html"), "it", "fast-house-milano-case-immobiliare")
    assert milan["name"] == "Fast House" and milan["properties_count"] == 74
    assert milan["default_listing_link"] == "https://www.idealista.it/pro/fast-house-milano-case-immobiliare/affitto-case/"


def test_agency_not_found_page():
    with pytest.raises(ValueError):
        P.parse_agency(fixture("agency_not_found.html"), "es", "does-not-exist-xyz")
    assert P.is_not_found_page(fixture("agency_not_found.html")) is True
    # an empty / past-the-end agency listing is a 404 that keeps the microsite
    assert P.is_not_found_page(fixture("agency_listings_past_end.html")) is False
    assert F.is_zero_results(fixture("agency_listings_past_end.html")) is True
    assert F.is_zero_results(fixture("agency_not_found.html")) is False


def test_directory():
    directory = P.parse_directory(fixture("agencies_directory_alicante.html"), "es")
    assert directory["title"] == "Real estate agents in Alicante province"
    assert len(directory["results"]) == 15
    card = directory["results"][0]
    assert card["id"] == "260436125" and card["slug"] == "lion-capitalgroup"
    assert card["link"] == "https://www.idealista.com/pro/lion-capitalgroup/"
    assert card["listings_link"] == "https://www.idealista.com/pro/lion-capitalgroup/venta-viviendas/alicante/"
    assert card["years_on_site"] == 2 and card["listings_count"] == 171
    assert card["price_range"] == {"min": 109000, "max": 5500000, "currency": "EUR"}
    assert card["publication_quality_percent"] == 87 and card["verified_reports"] == 75
    assert card["reports_last_3_months"] == 165 and card["first_page_listings"] == 10
    assert card["speaks_your_language"] is True and card["location_id"] == "0-EU-ES-03"
    assert len(card["sample_pictures"]) == 3
    milan = P.parse_directory(fixture("agencies_directory_milano_it.html"), "it")
    assert len(milan["results"]) == 15 and milan["results"][0]["link"].startswith("https://www.idealista.it/pro/")


def test_directory_index():
    index = P.parse_directory_index(fixture("agencies_directory_index.html"), "es")
    slugs = {row["slug"] for row in index}
    assert {"madrid-provincia", "madrid-madrid", "balears-illes/mallorca", "alicante"} <= slugs
    assert len(index) == 85
    assert P.parse_directory_index(fixture("agencies_directory_index_it.html"), "it")[0]["slug"] == "chieti-provincia"
    assert P.parse_directory("<html></html>", "es") == {"title": None, "results": []}


# ---- typeahead -------------------------------------------------------------------------

def test_suggestions():
    rows = P.parse_suggestions(fixture("suggest_madr.json"), "es")
    assert rows[0] == {"name": "Madrid, Madrid", "id": "0-EU-ES-28-07-001-079", "slug": "madrid-madrid",
                       "link": "https://www.idealista.com/venta-viviendas/madrid-madrid/", "type": "Municipality",
                       "parent_id": "0-EU-ES-28", "listings_count": 19830, "has_child_zones": True,
                       "is_zone_of_interest": False, "is_postcode": False}
    postcode = P.parse_suggestions(fixture("suggest_postcode_28013.json"), "es")[0]
    assert postcode["slug"] == "geo/codigo-postal-28013" and postcode["is_postcode"] is True
    assert postcode["id"] is None and postcode["listings_count"] == 292
    rooms = P.parse_suggestions(fixture("suggest_rent_room_madr.json"), "es")
    assert rooms[0]["link"] == "https://www.idealista.com/alquiler-habitacion/madrid-madrid/"
    assert P.parse_suggestions(fixture("suggest_empty.json"), "es") == []
    assert P.parse_suggestions(None, "es") == []


# ---- block detection -------------------------------------------------------------------

def test_datadome_page_is_recognised():
    assert F.is_datadome(fixture("blocked_datadome.html")) is True
    assert F.is_datadome(fixture("list_sale_madrid.html")) is False
    assert F.page_title(fixture("blocked_datadome.html")) == "idealista.com"


def test_several_areas_on_one_line():
    """A villa's 'Basic features' line carries built and usable area together
    (detail 111201434, 2026-11-02): each number takes the label after it."""
    facts = P._parse_lines(["Detached house", "3 floors", "1,478 m² built, 1,256 m² floor area",
                            "7 bedrooms", "10 bathrooms", "Land plot of 2,047 m²"])
    assert facts["size_m2"] == 1478 and facts["usable_size_m2"] == 1256 and facts["plot_size_m2"] == 2047
    assert facts["rooms"] == 7 and facts["bathrooms"] == 10
    assert P._parse_lines(["657 m² of surface area"])["size_m2"] == 657


def test_detail_typology_maps_to_a_public_property_type():
    assert P._public_type("chalet") == "homes"        # villas / houses on detail pages
    assert P._public_type("home") == "homes" and P._public_type("office") == "offices"
    assert P._public_type("room") == "rooms" and P._public_type(None) is None
    assert P._public_type("something-new") is None    # raw value stays in `typology`
