"""End-to-end pipeline assertions for CartMind."""

from catalog_service import CatalogService
from cart_service import CartService
from gating import GatingService
from mandate import IntentMandate
from razorpay_service import RazorpayService


def run_happy_path():
    catalog = CatalogService()
    cart = CartService(catalog.products)
    gate = GatingService()
    service = RazorpayService()

    result = catalog.search("running shoes")
    assert result and len(result) >= 1, "No products found for happy-path search"

    cart.add_item(result[0]["sku"], 1)
    cart_total = cart.get_total(catalog.products)
    assert cart_total > 0, "Cart total should be positive"

    intent = IntentMandate(
        user_id="user_123",
        merchant_id="merchant_demo",
        amount=cart_total,
        description="Buy a running shoe",
        authorized_by="user_123",
    )
    checkout = gate.create_cart_mandate(intent, cart, catalog.products)
    assert checkout is not None, "Checkout mandate should be created"
    assert checkout.authorized_by == "user_123", "Cart mandate must record the authorizer"

    gate.confirm_cart(checkout, "yes, confirm this cart")
    accepted, result = gate.check_cart_against_policy(checkout)
    assert accepted is True, "Cart should pass gating in happy path"

    payment_result = service.create_order({
        "amount": int(cart_total * 100),
        "currency": "INR",
        "receipt": "happy-path",
    })
    assert payment_result["status"] in {"created", "paid", "success"}, "Payment creation failed"
    print("Happy path audit trail:")
    gate.render_trail()
    return True


def run_blocked_path():
    catalog = CatalogService()
    cart = CartService(catalog.products)
    gate = GatingService()

    watch = next((p for p in catalog.products if p.get("category") == "accessories"), None)
    assert watch is not None, "Expected a demo blocked accessory item in catalog"

    cart.add_item(watch["sku"], 1)
    intent = IntentMandate(
        user_id="user_123",
        merchant_id="merchant_demo",
        amount=cart.get_total(catalog.products),
        description="Buy watch",
        authorized_by="user_123",
    )
    checkout = gate.create_cart_mandate(intent, cart, catalog.products)
    accepted, result = gate.check_cart_against_policy(checkout)
    assert accepted is False, "Blocked accessory cart should be rejected"
    assert result.get("reason") and "blocked" in result["reason"].lower(), "Blocked reason missing"
    print("Blocked-path audit trail:")
    gate.render_trail()
    return True


def run_decline_path():
    catalog = CatalogService()
    cart = CartService(catalog.products)
    gate = GatingService()
    service = RazorpayService()

    item = next((p for p in catalog.products if p["sku"] == "AUD-021"), None)
    assert item is not None, "Expected an allowed speaker product for graceful decline test"
    cart.add_item(item["sku"], 1)

    intent = IntentMandate(
        user_id="user_123",
        merchant_id="merchant_demo",
        amount=cart.get_total(catalog.products),
        description="Buy speaker",
        authorized_by="user_123",
    )
    checkout = gate.create_cart_mandate(intent, cart, catalog.products)
    gate.confirm_cart(checkout, "Yes, proceed to payment.")
    accepted, _ = gate.check_cart_against_policy(checkout)
    assert accepted is True, "Regular cart should be allowed"

    payment_result = service.create_order({
        "amount": int(cart.get_total(catalog.products) * 100),
        "currency": "INR",
        "receipt": "decline-path",
        "force_fail": True,
    })
    assert payment_result["status"] == "failed", "Forced failure should fail gracefully"
    print("Graceful-decline audit trail:")
    gate.render_trail()
    return True


if __name__ == "__main__":
    print("Running happy path")
    run_happy_path()
    print("Happy path passed")

    print("Running blocked-path scenario")
    run_blocked_path()
    print("Blocked path passed")

    print("Running graceful-decline scenario")
    run_decline_path()
    print("Graceful decline passed")

    print("All pipeline checks passed.")
