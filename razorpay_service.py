import os
from typing import Any, Dict, Optional


class RazorpayService:
    """Wrap Razorpay's Python SDK when available, else use a local simulator.

    The real SDK requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in the process
    environment. In a local demo, those may be absent; we still want the rest of
    the application to use the same method names and result shape.
    """

    def __init__(self, key_id: Optional[str] = None, key_secret: Optional[str] = None):
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID")
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET")
        self.use_simulator = not bool(self.key_id and self.key_secret)

        try:
            import razorpay  # noqa: F401
            self.client = None if self.use_simulator else razorpay.Client(auth=(self.key_id, self.key_secret))
        except Exception:
            self.client = None
            self.use_simulator = True

    def _simulate_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        force_fail = bool(payload.get("force_fail", False))
        amount = int(payload.get("amount", 0))
        currency = str(payload.get("currency", "INR")).upper()
        status = "failed" if force_fail else "created"
        if not force_fail and amount > 0:
            status = "paid"

        return {
            "id": f"order_{abs(hash(str(payload))) % 1000000}",
            "entity": "order",
            "amount": amount,
            "currency": currency,
            "status": status,
            "receipt": payload.get("receipt", "demo_receipt"),
            "notes": payload.get("notes", {}),
            "method": payload.get("method", "card"),
            "descriptor": payload.get("descriptor", "CartMind Demo"),
        }

    def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.use_simulator:
            return self._simulate_order(payload)

        if self.client is None:
            return self._simulate_order(payload)

        order_payload = dict(payload)
        order_payload.pop("force_fail", None)
        try:
            result = self.client.order.create(order_payload)
            return {
                "id": result.get("id"),
                "entity": result.get("entity", "order"),
                "amount": result.get("amount"),
                "currency": result.get("currency", "INR"),
                "status": result.get("status", "created"),
                "receipt": result.get("receipt", "demo_receipt"),
            }
        except Exception as exc:
            return {
                "id": None,
                "entity": "order",
                "amount": int(payload.get("amount", 0)),
                "currency": str(payload.get("currency", "INR")).upper(),
                "status": "failed",
                "error": str(exc),
            }

    def capture_payment(self, order_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        if self.use_simulator:
            return {
                "id": f"pay_{order_id}",
                "entity": "payment",
                "status": "captured" if not payload.get("force_fail") else "failed",
                "order_id": order_id,
            }

        if self.client is None:
            return {
                "id": f"pay_{order_id}",
                "entity": "payment",
                "status": "captured" if not payload.get("force_fail") else "failed",
                "order_id": order_id,
            }

        try:
            result = self.client.payment.capture(order_id, payload.get("amount", 0), payload.get("currency", "INR"))
            return {
                "id": result.get("id"),
                "entity": result.get("entity", "payment"),
                "status": result.get("status", "captured"),
                "order_id": order_id,
            }
        except Exception as exc:
            return {
                "id": None,
                "entity": "payment",
                "status": "failed",
                "order_id": order_id,
                "error": str(exc),
            }

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        if self.use_simulator or self.client is None:
            return False
        try:
            self.client.utility.verify_payment_signature({
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
            return True
        except Exception:
            return False


if __name__ == "__main__":
    service = RazorpayService()
    print(service.create_order({"amount": 12300, "currency": "INR", "receipt": "demo"}))
