import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gating import GatingService
from mandate import IntentMandate

CATALOG = [
    {"sku": "SKU-1", "name": "Headphones", "category": "electronics", "price_inr": 1000},
    {"sku": "SKU-2", "name": "Phone Case", "category": "accessories", "price_inr": 500},
]


class FakeCart:
    def __init__(self, items):
        self._items = items

    def get_items(self):
        return self._items

    def get_total(self, catalog):
        by_sku = {p["sku"]: p for p in catalog}
        return sum(by_sku[sku]["price_inr"] * qty for sku, qty in self._items.items())


def make_intent():
    return IntentMandate(user_id="u1", merchant_id="merchant_demo", amount=0, description="test", authorized_by="u1@example.com")


def test_create_cart_mandate_computes_total_and_categories():
    gate = GatingService()
    mandate = gate.create_cart_mandate(make_intent(), FakeCart({"SKU-1": 2}), CATALOG)
    assert mandate.amount == 2000
    assert mandate.items[0]["category"] == "electronics"


def test_confirm_cart_requires_explicit_language():
    gate = GatingService()
    mandate = gate.create_cart_mandate(make_intent(), FakeCart({"SKU-1": 1}), CATALOG)
    assert gate.confirm_cart(mandate, "maybe later") is False
    assert mandate.user_confirmation is False
    assert gate.confirm_cart(mandate, "yes, confirm this cart") is True
    assert mandate.user_confirmation is True


def test_policy_blocks_empty_cart():
    gate = GatingService()
    mandate = gate.create_cart_mandate(make_intent(), FakeCart({}), CATALOG)
    accepted, result = gate.check_cart_against_policy(mandate)
    assert accepted is False
    assert "empty" in result["reason"].lower()


def test_policy_blocks_accessories_category():
    gate = GatingService()
    mandate = gate.create_cart_mandate(make_intent(), FakeCart({"SKU-2": 1}), CATALOG)
    gate.confirm_cart(mandate, "yes")
    accepted, result = gate.check_cart_against_policy(mandate)
    assert accepted is False
    assert "accessories" in result["reason"].lower()


def test_policy_blocks_over_max_order_value():
    gate = GatingService()
    mandate = gate.create_cart_mandate(make_intent(), FakeCart({"SKU-1": 10}), CATALOG)  # 10,000 > MAX_ORDER_VALUE
    gate.confirm_cart(mandate, "yes")
    accepted, result = gate.check_cart_against_policy(mandate)
    assert accepted is False
    assert "exceeds" in result["reason"].lower()


def test_policy_blocks_without_confirmation():
    gate = GatingService()
    mandate = gate.create_cart_mandate(make_intent(), FakeCart({"SKU-1": 1}), CATALOG)
    accepted, result = gate.check_cart_against_policy(mandate)
    assert accepted is False
    assert "confirmation" in result["reason"].lower()


def test_policy_allows_valid_confirmed_cart():
    gate = GatingService()
    mandate = gate.create_cart_mandate(make_intent(), FakeCart({"SKU-1": 1}), CATALOG)
    gate.confirm_cart(mandate, "yes, confirm")
    accepted, result = gate.check_cart_against_policy(mandate)
    assert accepted is True
    assert result["blocked"] is False


def test_audit_log_records_each_step():
    gate = GatingService()
    mandate = gate.create_cart_mandate(make_intent(), FakeCart({"SKU-1": 1}), CATALOG)
    gate.confirm_cart(mandate, "yes")
    gate.check_cart_against_policy(mandate)
    steps = [record["action"] for record in gate.audit_log]
    assert steps == ["create_cart_mandate", "confirm_cart", "check_cart_against_policy"]
