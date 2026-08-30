from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mandate import CartMandate


class GatingService:
    """Bounded, gated, explainable, and auditable payment controls.

    This is the highest-priority safety layer in the demo. The reason it exists is
    simple: AI agents are capable of making money-moving actions very quickly, but
    that speed means the application must insert an explicit review step before any
    settlement is attempted. The AP2-inspired pattern here is Intent -> Cart ->
    Payment, where each step is a separate object and a separate gate.

    The checks below are intentionally plain-English and auditable, so a reviewer
    can see why a transaction was allowed or blocked without needing to inspect the
    model's hidden reasoning.
    """

    MAX_ORDER_VALUE = 5000
    BLOCKED_CATEGORIES = {"accessories"}

    def __init__(self):
        self.audit_log: List[Dict[str, Any]] = []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _record_audit(self, step: str, action: str, reasoning: str, amount: float, status: str):
        """Write a structured, timestamped event for later presentation."""
        self.audit_log.append({
            "timestamp": self._now_iso(),
            "step": step,
            "action": action,
            "reasoning": reasoning,
            "amount": amount,
            "status": status,
        })

    def create_cart_mandate(self, intent, cart, catalog=None):
        """Create a structured cart object from the current cart state.

        The key idea is that a cart is not the same as a payment. We first lock in
        the intended purchase—what is in the cart, for how much, and by whom—before
        the merchant or user checks whether it should proceed.
        """
        catalog = catalog or getattr(cart, "catalog", [])
        items = []
        for sku, qty in cart.get_items().items():
            item = {"sku": sku, "quantity": qty}
            product = next((p for p in catalog if p.get("sku") == sku), None)
            if product:
                item["category"] = product.get("category", "unknown")
                item["name"] = product.get("name", sku)
                item["unit_price_inr"] = int(product.get("price_inr", 0))
            items.append(item)

        total = float(cart.get_total(catalog))
        mandate = CartMandate(
            cart_id=f"cart_{int(datetime.now(timezone.utc).timestamp())}",
            user_id=getattr(intent, "user_id", "unknown_user"),
            merchant_id=getattr(intent, "merchant_id", "merchant_demo"),
            items=items,
            amount=total,
            currency="INR",
            authorized_by=getattr(intent, "authorized_by", ""),
            expires_at=None,
            constraints={
                "max_order_value": self.MAX_ORDER_VALUE,
                "blocked_categories": sorted(self.BLOCKED_CATEGORIES),
            },
        )
        self._record_audit(
            "cart",
            "create_cart_mandate",
            "User intent captured before any payment is attempted.",
            total,
            "created",
        )
        return mandate

    def confirm_cart(self, cart_mandate: CartMandate, user_message: str):
        """Record explicit user approval for the cart.

        This is the requirement that prevents silent charging. A payment can only
        happen after a message from the user that clearly says yes or confirms the
        cart. Ambiguous language is treated as blocked.
        """
        user_text = (user_message or "").strip().lower()
        if not user_text or not any(token in user_text for token in ["yes", "confirm", "approve", "ok", "proceed"]):
            self._record_audit(
                "cart",
                "confirm_cart",
                "Confirmation missing or ambiguous; payment remains blocked.",
                float(cart_mandate.amount),
                "blocked",
            )
            return False

        cart_mandate.user_confirmation = True
        cart_mandate.confirmation_reason = user_message.strip()
        self._record_audit(
            "cart",
            "confirm_cart",
            "Explicit user confirmation recorded against the cart mandate.",
            float(cart_mandate.amount),
            "confirmed",
        )
        return True

    def check_cart_against_policy(self, cart_mandate: CartMandate):
        """Validate the cart against the merchant's bounded payment rules.

        This function intentionally returns plain English reasons rather than a
        generic boolean because the application is meant to be explainable. A judge
        or reviewer can see exactly which rule blocked the transaction.
        """
        amount = float(getattr(cart_mandate, "amount", 0))
        items = getattr(cart_mandate, "items", [])

        if not items:
            self._record_audit("cart", "check_cart_against_policy", "Cart is empty; no payment can be attempted.", amount, "blocked")
            return False, {"blocked": True, "reason": "Cart is empty; nothing to buy."}

        for item in items:
            category = str(item.get("category", "")).lower()
            if category in self.BLOCKED_CATEGORIES:
                self._record_audit("cart", "check_cart_against_policy", "Blocked category detected: accessories are not allowed in this demo.", amount, "blocked")
                return False, {"blocked": True, "reason": "Blocked category detected: accessories are not allowed in this demo."}

        if amount > self.MAX_ORDER_VALUE:
            self._record_audit("cart", "check_cart_against_policy", f"Order exceeds max allowed value of ₹{self.MAX_ORDER_VALUE}.", amount, "blocked")
            return False, {"blocked": True, "reason": f"Order is blocked: exceeds max allowed value of ₹{self.MAX_ORDER_VALUE}."}

        if not getattr(cart_mandate, "user_confirmation", False):
            self._record_audit("cart", "check_cart_against_policy", "Payment blocked because no explicit prior user confirmation was recorded against the cart.", amount, "blocked")
            return False, {"blocked": True, "reason": "Payment blocked because no explicit prior user confirmation was recorded against the cart."}

        self._record_audit("cart", "check_cart_against_policy", "Cart passes bounds and confirmation checks.", amount, "allowed")
        return True, {"blocked": False, "reason": "Cart passes bounds and confirmation checks."}

    def render_trail(self):
        """Print the structured audit log in a readable table."""
        if not self.audit_log:
            print("No audit records yet.")
            return

        print("\nAudit Trail")
        print("-" * 115)
        headers = ["timestamp", "step", "action", "reasoning", "amount", "status"]
        widths = {
            key: max(len(str(key)), max(len(str(record.get(key, ""))) for record in self.audit_log))
            for key in headers
        }
        print(" | ".join(str(key).ljust(widths[key]) for key in headers))
        print("-" * 115)
        for record in self.audit_log:
            print(" | ".join(str(record.get(key, "")).ljust(widths[key]) for key in headers))
        print("-" * 115)

    def clear_audit(self):
        self.audit_log.clear()


if __name__ == "__main__":
    gate = GatingService()
    gate._record_audit("demo", "example", "Sample audit row", 1200, "ok")
    gate.render_trail()
