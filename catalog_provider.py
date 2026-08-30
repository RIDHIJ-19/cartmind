import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class DummyJsonCatalog:
    """Optional discovery source for demos; never used as the price authority."""

    base_url = "https://dummyjson.com/products"

    def search(self, query="", limit=12):
        params = {"limit": limit}
        if query.strip():
            params["q"] = query.strip()
            url = f"{self.base_url}/search?{urlencode(params)}"
        else:
            url = f"{self.base_url}?{urlencode(params)}"

        request = Request(url, headers={"User-Agent": "CartMind/1.0 demo catalog client"})
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))

        return [
            {
                "external_id": item.get("id"),
                "name": item.get("title", "Untitled product"),
                "description": item.get("description", ""),
                "category": item.get("category", "other"),
                "price_usd": item.get("price", 0),
                "image": item.get("thumbnail", ""),
                "source": "DummyJSON",
            }
            for item in payload.get("products", [])
        ]