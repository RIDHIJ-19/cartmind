from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class IntentMandate:
    """Simplified AP2-inspired intent step.

    Real AP2 mandates are cryptographically signed verifiable credentials. This is
    a local demo stand-in that keeps the same conceptual shape: a user intent is
    explicitly recorded before a cart or payment action is permitted.
    """

    mandate_type: str = "intent"
    mandate_id: str = field(default_factory=lambda: f"int_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    user_id: str = ""
    merchant_id: str = ""
    amount: float = 0.0
    currency: str = "INR"
    description: str = ""
    issued_at: str = field(default_factory=utc_now_iso)
    authorized_by: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CartMandate:
    """Simplified AP2-inspired cart step with explicit confirmation tracking."""

    mandate_type: str = "cart"
    mandate_id: str = field(default_factory=lambda: f"cart_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    cart_id: str = ""
    user_id: str = ""
    merchant_id: str = ""
    items: List[Dict[str, Any]] = field(default_factory=list)
    amount: float = 0.0
    currency: str = "INR"
    issued_at: str = field(default_factory=utc_now_iso)
    expires_at: Optional[str] = None
    authorized_by: str = ""
    user_confirmation: bool = False
    confirmation_reason: Optional[str] = None
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PaymentMandate:
    """Simplified AP2-inspired payment step.

    The important property is that payment is only permitted after an explicit
    user confirmation already exists against the cart mandate.
    """

    mandate_type: str = "payment"
    mandate_id: str = field(default_factory=lambda: f"pay_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    cart_id: str = ""
    user_id: str = ""
    merchant_id: str = ""
    amount: float = 0.0
    currency: str = "INR"
    issued_at: str = field(default_factory=utc_now_iso)
    authorized_by: str = ""
    confirmed: bool = False
    payment_method: str = "razorpay"
    gateway_reference: Optional[str] = None
