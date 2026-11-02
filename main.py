"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does (paged endpoints carry a
`pagination` block instead of next / previous links); results are written
to output/*.json. The schemas fill in every default, exactly as the API does.
"""
import json
import os

from idealista import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def params(schema_cls, **query):
    """Validate a query exactly like the API: defaults filled, links resolved."""
    return schema_cls().load(query)


if __name__ == "__main__":
    # a listing id or any idealista.com / idealista.it listing link
    save("property_111201434.json", api.property_details(
        **params(schemas.PropertyDetailsSchema, property="111201434")))

    # 30 listings per page; a place name, postcode, slug or search link
    save("search_barcelona.json", api.properties_search(
        **params(schemas.PropertiesSearchSchema, location="Barcelona", features="terrace", sort="newest")))

    # an agency slug or any /pro/<slug>/ link
    save("agency_engel_volkers_marbella.json", api.agency_details(
        **params(schemas.AgencyDetailsSchema, agency="engel-volkers-marbella")))
