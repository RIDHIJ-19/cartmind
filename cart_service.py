class CartService:
    """Simple in-memory cart keyed by SKU, with totals in INR."""

    def __init__(self, catalog=None):
        self.catalog = catalog or []
        self.items = {}

    def set_catalog(self, catalog):
        self.catalog = catalog or []

    def add_item(self, sku, quantity=1):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.items[sku] = self.items.get(sku, 0) + quantity

    def remove_item(self, sku, quantity=None):
        if sku not in self.items:
            return False
        if quantity is None or quantity >= self.items[sku]:
            del self.items[sku]
        else:
            self.items[sku] -= quantity
            if self.items[sku] <= 0:
                del self.items[sku]
        return True

    def update_quantity(self, sku, quantity):
        if quantity <= 0:
            return self.remove_item(sku)
        self.items[sku] = quantity
        return True

    def get_items(self):
        return dict(self.items)

    def get_total(self, catalog=None):
        products = catalog or self.catalog
        total = 0
        for sku, qty in self.items.items():
            product = next((p for p in products if p.get("sku") == sku), None)
            if product:
                total += int(product.get("price_inr", 0)) * int(qty)
        return total

    def to_dict(self):
        lines = []
        for sku, qty in self.items.items():
            product = next((p for p in self.catalog if p.get("sku") == sku), None)
            lines.append({
                "sku": sku,
                "quantity": qty,
                "name": product.get("name") if product else sku,
                "unit_price_inr": product.get("price_inr") if product else 0,
                "line_total_inr": (product.get("price_inr") if product else 0) * qty,
            })
        return {"items": lines, "total_inr": self.get_total()}

    def clear(self):
        self.items.clear()

    def __len__(self):
        return len(self.items)

    def __bool__(self):
        return bool(self.items)
