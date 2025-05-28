import requests
from logement.models import Logement

API_KEY = "..."
API_SECRET = "..."
BASE_URL = "https://api.hostaway.com/v1"


API_KEY = "your_key"
API_SECRET = "your_secret"
BASE_URL = "https://api.hostaway.com/v1"


def get_dynamic_prices(listing_id, start_date, end_date):
    headers = {"Authorization": f"Bearer {API_KEY}:{API_SECRET}"}
    response = requests.get(
        f"{BASE_URL}/prices",
        headers=headers,
        params={"listingId": listing_id, "startDate": start_date, "endDate": end_date},
    )
    return response.json()


def fetch_hostaway_listings():
    headers = {"Authorization": f"Bearer {API_KEY}:{API_SECRET}"}
    response = requests.get(f"{BASE_URL}/listings", headers=headers)
    data = response.json()
    return data["result"]


def auto_link_logements():
    hostaway_logements = fetch_hostaway_listings()

    for h in hostaway_logements:
        name = h["name"]
        listing_id = h["id"]

        logement = Logement.objects.filter(name__iexact=name).first()
        if logement:
            logement.hostaway_listing_id = listing_id
            logement.save(update_fields=["hostaway_listing_id"])