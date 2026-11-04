# 🏡 Idealista Scraper

Idealista Scraper is a **free and open-source** scraper that gets you **unlimited** detailed idealista property data for free.

## ✨ What Can I Get?

- 🏡 **Full details on 1.1M+ Spanish listings** — price, €/m², size, rooms, energy rating, GPS, photos & video
- 🔍 **Search Spain & Italy your way** — any city, district or postcode, 14 filters, sale or rent
- 🗺️ **Draw your own search area** — any polygon on the map, with the same filters
- 🏢 **Agencies & their listings** — profiles, addresses, languages, quality scores & every property they list

## 🎥 Example: A Full Idealista Listing

```json
{
  "id": "111201434",
  "link": "https://www.idealista.com/inmueble/111201434/",
  "title": "Detached house for sale in Calle Liszt",
  "subtitle": "Sierra Blanca, Marbella",
  "operation": "sale",
  "price": { "amount": 22000000, "currency": "EUR", "period": null, "text": "22,000,000 €" },
  "price_per_m2": 14885,
  "size_m2": 1478,
  "plot_size_m2": 2047,
  "rooms": 7,
  "bathrooms": 10,
  "orientation": "South",
  "parking": "included",
  "has_swimming_pool": true,
  "has_garden": true,
  "tags": ["Sea views", "Luxury", "Villa"],
  "energy_certificate": { "rating": "C", "consumption_kwh_m2_year": 75.0, "emissions_kg_co2_m2_year": 25.0 },
  "description": {
    "text": "Grand Residence with panoramic sea views in Sierra Blanca\nCompleted in 2024, this exceptional newly built villa in Sierra Blanca represents one of Marbella’s most exclusive residences...",
    "language": "en",
    "is_translated": false
  },
  "location": { "address": "Calle Liszt", "area": "Sierra Blanca", "district": "Nagüeles-Milla de Oro", "city": "Marbella", "latitude": 36.5257845, "longitude": -4.9083286 },
  "photos": [
    { "id": 1428869304, "link": "https://img4.idealista.com/blur/WEB_DETAIL/0/id.pro.es.image.master/22/4b/4c/1428869304.jpg", "tag": "Facade", "width": 1500, "height": 844 }
  ],
  "photos_count": 59,
  "videos": [
    { "link": "https://st3v.idealista.com/50/23/03/1446803246.mp4", "hd_link": "https://st3v.idealista.com/50/23/03/hd_1446803246.mp4" }
  ],
  "updated_date": "2026-09-01",
  "advertiser": {
    "type": "professional",
    "agency": { "name": "Engel & Völkers Marbella", "slug": "engel-volkers-marbella", "link": "https://www.idealista.com/pro/engel-volkers-marbella/" }
  }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Idealista Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/idealista-scraper
cd idealista-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

idealista's DataDome bot protection refuses some IPs outright (mobile carriers, many cloud servers). Getting `blocked` errors? Start it on a Spanish residential proxy instead:
```bash
IDEALISTA_PROXY=http://user:pass@host:port python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/properties/details?property=111201434"
```

```json
{
  "id": "111201434",
  "title": "Detached house for sale in Calle Liszt",
  "subtitle": "Sierra Blanca, Marbella",
  "operation": "sale",
  "property_type": "homes",
  "price": { "amount": 22000000, "currency": "EUR", "period": null, "text": "22,000,000 €" },
  "price_per_m2": 14885,
  "size_m2": 1478,
  "usable_size_m2": 1256,
  "plot_size_m2": 2047,
  "rooms": 7,
  "bathrooms": 10,
  "has_swimming_pool": true,
  "tags": ["Sea views", "Luxury", "Villa"],
  "location": { "city": "Marbella", "area": "Sierra Blanca", "latitude": 36.5257845, "longitude": -4.9083286 },
  "photos_count": 59,
  "advertiser": { "type": "professional", "agency": { "name": "Engel & Völkers Marbella", "slug": "engel-volkers-marbella" } }
}
```

All 7 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

7 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Property Details | `/properties/details` | Everything about one listing: price, specs, GPS, photos, video |
| Search Locations | `/locations/search` | Location slugs and IDs for any Spanish or Italian place |
| Search Properties | `/properties/search` | 30 listings per page with 14 filters and 11 sort orders |
| Search Map Area | `/properties/shape` | Every listing inside a polygon you draw, 30 per page |
| Search Agencies | `/agencies/search` | Top agencies of any city, with listing counts and price ranges |
| Agency Details | `/agencies/details` | Address, languages, listing count, quality score and video |
| Agency Properties | `/agencies/properties` | Every listing of one agency, filtered your way, 30 per page |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-idealista-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-idealista-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-idealista-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/properties/details",
    params={"property": "111201434"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Idealista Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/idealista-scraper-github-whatsapp)

[![Ask Us by Email about Idealista Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Idealista%20Scraper%20API&body=I%20need%20help%20using%20the%20Idealista%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/idealista-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/idealista-scraper)
