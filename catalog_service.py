import json
from pathlib import Path


class CatalogService:
    """Search and rank product records in the merchant catalog."""

    def __init__(self, catalog_path=None):
        base_dir = Path(__file__).resolve().parent
        self.catalog_path = Path(catalog_path) if catalog_path else base_dir / "catalog.json"
        self.products = self._load_catalog()

    def _load_catalog(self):
        with open(self.catalog_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def search(self, query, limit=5):
        """Return ranked products whose names or tags match the query."""
        if not query or not query.strip():
            return [self._product_result(p, "All items currently available") for p in self.products[:limit]]

        query_terms = query.lower().strip().split()
        ranked = []

        for p in self.products:
            haystack = " ".join([
                p.get("name", ""),
                p.get("category", ""),
                p.get("brand", ""),
                " ".join(p.get("tags", [])),
                p.get("description", ""),
            ]).lower()

            score = 0
            for term in query_terms:
                if term in haystack:
                    score += 2
                if term in p.get("name", "").lower():
                    score += 5
                if term in p.get("category", "").lower():
                    score += 4
                if term in " ".join(p.get("tags", [])).lower():
                    score += 2

            if score > 0:
                ranked.append((p, score))

        ranked.sort(key=lambda item: item[1], reverse=True)
        results = []
        for product, _ in ranked[:limit]:
            results.append(self._product_result(product, self._build_reason(product, query_terms)))

        return results

    @staticmethod
    def _build_reason(product, query_terms):
        matches = []
        for term in query_terms:
            if term.lower() in product.get("name", "").lower():
                matches.append(f"name match {term}")
            if term.lower() in product.get("category", "").lower():
                matches.append(f"category match {term}")
            if term.lower() in " ".join(product.get("tags", [])).lower():
                matches.append(f"tag match {term}")
        if not matches:
            return f"Relevant for {', '.join(query_terms)}."
        return "Matched: " + "; ".join(matches)

    @staticmethod
    def _product_result(product, reason):
        return {
            "sku": product["sku"],
            "name": product["name"],
            "category": product["category"],
            "brand": product["brand"],
            "price_inr": product["price_inr"],
            "description": product["description"],
            "reason": reason,
        }


if __name__ == "__main__":
    service = CatalogService()
    for item in service.search("headphones"):
        print(item)
