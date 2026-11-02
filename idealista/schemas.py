"""Marshmallow request schemas for every /idealista/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    property   a numeric ad id (109630900) OR any idealista listing link
    agency     a microsite slug (walterhauschamberi) OR any /pro/<slug>/ link
    location   a place name ("Chamberí, Madrid"), a postcode, a location slug
               from locations/search ("madrid-madrid", "madrid/chamberi") OR
               any idealista search link (its filters and page are kept)
    shape      a polygon "lat,lng;lat,lng;…" (3+ points) OR a drawn-area link

`country` picks the market (es = www.idealista.com, it = www.idealista.it;
a link overrides it). `language` picks the rendering locale of the texts
(the site auto-translates descriptions; Spanish itself is unavailable over
plain HTTP — see idealista/fetch.py).

The filter vocabularies are idealista's own filter form (idealista/refs.py,
captured 2026-10-30).
"""
from marshmallow import ValidationError, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CommaListField, Flag, PageField, PositiveInt,
                           QueryField, RefField, StrippedString)
from idealista import refs


class PropertyRefField(RefField):
    resolver = staticmethod(refs.resolve_property)


class AgencyRefField(RefField):
    resolver = staticmethod(refs.resolve_agency)


class ShapeField(RefField):
    resolver = staticmethod(refs.resolve_shape)


class LocationField(StrippedString):
    """Classifies the value (link / slug / name) without network; api.py
    resolves names through the site's typeahead."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        try:
            refs.classify_location(value)
        except ValueError as e:
            raise ValidationError(str(e))
        return value


def _country():
    return ChoiceField(list(refs.SITES), load_default=refs.DEFAULT_COUNTRY, metadata={
        "description": "market: es (www.idealista.com, Spain) or it (www.idealista.it, Italy); a link in another param overrides it"})


def _language():
    return ChoiceField(list(refs.LANGUAGES), load_default=refs.DEFAULT_LANGUAGE, metadata={
        "description": "language of the texts (en, fr, de, it, pt, nl, ru); descriptions are auto-translated by idealista"})


def _operation():
    return ChoiceField(list(refs.OPERATIONS), load_default="sale", metadata={"description": "sale or rent"})


def _property_type():
    return ChoiceField(list(refs.PROPERTY_TYPES), load_default="homes", metadata={
        "description": "homes, rooms (rent only), new_developments (sale only), offices, premises, transfers "
                       "(sale only), garages, lands, storage_rooms or buildings"})


class _FilterMixin:
    """The search filters shared by properties/search, properties/shape and
    agencies/properties (idealista's own filter form)."""
    min_price = PositiveInt(metadata={"description": "minimum price in EUR (monthly rent for rentals)"})
    max_price = PositiveInt(metadata={"description": "maximum price in EUR (monthly rent for rentals)"})
    min_size = PositiveInt(metadata={"description": "minimum built area in m²"})
    max_size = PositiveInt(metadata={"description": "maximum built area in m²"})
    bedrooms = CommaListField(allowed=refs.BEDROOMS, upper=False, max_items=5, metadata={
        "description": "bedroom counts, comma-separated: 0 (studio), 1, 2, 3, 4 (four or more)"})
    bathrooms = CommaListField(allowed=refs.BATHROOMS, upper=False, max_items=3, metadata={
        "description": "bathroom counts, comma-separated: 1, 2, 3 (three or more)"})
    home_type = CommaListField(allowed=list(refs.HOME_TYPES), upper=False, max_items=13, metadata={
        "description": "home subtypes, comma-separated: flat, apartment, penthouse, duplex, loft, attic, house, "
                       "detached, semi_detached, terraced, country_house, villa, single_storey"})
    condition = CommaListField(allowed=list(refs.CONDITIONS), upper=False, max_items=3, metadata={
        "description": "new_build, good, needs_renovation (comma-separated)"})
    features = CommaListField(allowed=list(refs.FEATURES), upper=False, max_items=20, metadata={
        "description": "required features, comma-separated: air_conditioning, wardrobes, lift, balcony, terrace, "
                       "balcony_or_terrace, exterior, parking, garden, swimming_pool, storage_room, accessible, luxury, "
                       "floor_plan, virtual_tour, bank_owned, pets_allowed, long_term, short_term"})
    furnished = ChoiceField(list(refs.FURNISHED), metadata={
        "description": "rentals: furnished or kitchen_only (fitted kitchen only)"})
    floor = CommaListField(allowed=list(refs.FLOORS), upper=False, max_items=3, metadata={
        "description": "floor levels, comma-separated: top, middle, ground"})
    energy_rating = CommaListField(allowed=list(refs.ENERGY_RATINGS), upper=False, max_items=3, metadata={
        "description": "energy certificate bands, comma-separated: high (A-B), medium (C-D), low (E-G)"})
    occupancy = CommaListField(allowed=list(refs.OCCUPANCY), upper=False, max_items=4, metadata={
        "description": "sales: free, tenanted, bare_ownership, squatted (comma-separated)"})
    published = ChoiceField(list(refs.PUBLISHED), metadata={
        "description": "only listings published in the last_48_hours, last_week or last_month"})
    sort = ChoiceField(list(refs.SORTS), metadata={
        "description": "price_asc, price_desc, newest, oldest, size_asc, size_desc, floor_asc, floor_desc, "
                       "price_per_m2_asc, price_per_m2_desc (Spain only), price_drop; default = idealista's own order"})

    @validates_schema
    def _price_and_size_ranges(self, data, **kwargs):
        if data.get("min_price") and data.get("max_price") and data["min_price"] > data["max_price"]:
            raise ValidationError("min_price must not exceed max_price.", "max_price")
        if data.get("min_size") and data.get("max_size") and data["min_size"] > data["max_size"]:
            raise ValidationError("min_size must not exceed max_size.", "max_size")
        if data.get("sort") and data.get("country") and data["country"] not in refs.SORTS[data["sort"]]:
            raise ValidationError(f"sort={data['sort']} is not offered on idealista.{data['country']}.", "sort")


class LocationsSearchSchema(BaseSchema):
    query = QueryField(max_length=80, metadata={
        "description": "place name prefix or postcode (Madr, Chamberí, 28013); idealista's own typeahead"})
    country = _country()
    operation = _operation()
    property_type = _property_type()
    language = _language()


class PropertiesSearchSchema(_FilterMixin, BaseSchema):
    location = LocationField(metadata={
        "description": "place name, postcode, a location slug from locations/search (madrid-madrid, "
                       "madrid/chamberi) or any idealista search link"})
    country = _country()
    operation = _operation()
    property_type = _property_type()
    page = PageField(max_page=refs.MAX_PAGES, metadata={
        "description": f"page of 30 results (idealista serves at most {refs.MAX_PAGES} pages per search)"})
    language = _language()


class PropertiesShapeSchema(_FilterMixin, BaseSchema):
    shape = ShapeField(metadata={
        "description": "polygon as 'lat,lng;lat,lng;…' (at least 3 points) or an idealista drawn-area link (…?shape=…)"})
    country = _country()
    operation = _operation()
    property_type = _property_type()
    page = PageField(max_page=refs.MAX_PAGES, metadata={
        "description": f"page of 30 results (idealista serves at most {refs.MAX_PAGES} pages per search)"})
    language = _language()


class PropertyDetailsSchema(BaseSchema):
    property = PropertyRefField(metadata={
        "description": "idealista listing id (109630900) or any listing link (…/inmueble/<id>/, …/immobile/<id>/)"})
    country = _country()
    language = _language()

    @validates_schema(pass_original=True)
    def _country_from_link(self, data, original, **kwargs):
        raw = (original or {}).get("property") if isinstance(original, dict) else None
        if raw:
            data["country"] = refs.property_country(str(raw), data.get("country") or refs.DEFAULT_COUNTRY)


class AgencyDetailsSchema(BaseSchema):
    agency = AgencyRefField(metadata={
        "description": "agency microsite slug (walterhauschamberi) or any idealista /pro/<slug>/ link"})
    country = _country()
    language = _language()

    @validates_schema(pass_original=True)
    def _country_from_link(self, data, original, **kwargs):
        raw = (original or {}).get("agency") if isinstance(original, dict) else None
        if raw:
            data["country"] = refs.agency_country(str(raw), data.get("country") or refs.DEFAULT_COUNTRY)


class AgencyPropertiesSchema(_FilterMixin, BaseSchema):
    agency = AgencyRefField(metadata={
        "description": "agency microsite slug (walterhauschamberi) or any idealista /pro/<slug>/ link"})
    country = _country()
    operation = _operation()
    property_type = _property_type()
    location = StrippedString(load_default=None, metadata={
        "description": "optional location slug to narrow the agency's listing (madrid-madrid, barcelona-provincia)"})
    page = PageField(max_page=refs.MAX_PAGES, metadata={"description": "page of 30 results"})
    language = _language()

    @validates_schema(pass_original=True)
    def _country_from_link(self, data, original, **kwargs):
        raw = (original or {}).get("agency") if isinstance(original, dict) else None
        if raw:
            data["country"] = refs.agency_country(str(raw), data.get("country") or refs.DEFAULT_COUNTRY)
        location = data.get("location")
        if location:
            kind, value = refs.classify_location(location)
            if kind != "slug":
                raise ValidationError("Must be a location slug such as madrid-madrid or barcelona-provincia.", "location")
            data["location"] = value


class AgenciesSearchSchema(BaseSchema):
    location = StrippedString(required=True, metadata={
        "description": "province or city: a name (Alicante, Madrid), a directory slug (madrid-provincia, "
                       "balears-illes/mallorca) or an idealista agencies-directory link"})
    country = _country()
    language = _language()

    @validates_schema(pass_original=True)
    def _link_country(self, data, original, **kwargs):
        raw = (original or {}).get("location") if isinstance(original, dict) else None
        if raw and refs._is_link(str(raw).strip()):
            try:
                country, path, _query = refs.parse_site_link(str(raw).strip())
            except ValueError as e:
                raise ValidationError(str(e), "location")
            data["country"] = country
            data["location"] = path
