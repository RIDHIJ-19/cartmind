from collections import defaultdict
from datetime import datetime, timezone


class InMemoryRateLimiter:
    """Default rate limiter: per-process, per-transaction sliding window.

    Only suitable for a single-process deployment or tests — under gunicorn
    with multiple workers each worker gets its own instance, so the
    effective attempt budget is multiplied by the worker count. Pass a
    shared/persistent limiter (e.g. one backed by the database) in
    multi-worker deployments.
    """

    def __init__(self):
        self.attempts = defaultdict(list)

    def record(self, transaction_id, timestamp):
        self.attempts[transaction_id].append(timestamp)

    def recent_count(self, transaction_id, now, window_seconds=60):
        recent = [stamp for stamp in self.attempts[transaction_id] if now - stamp < window_seconds]
        self.attempts[transaction_id] = recent
        return len(recent)


class DatabaseRateLimiter:
    """Rate limiter backed by CartMindDatabase, shared across gunicorn workers
    and process restarts (unlike InMemoryRateLimiter)."""

    def __init__(self, database):
        self.database = database

    def record(self, transaction_id, timestamp):
        self.database.record_payment_attempt(transaction_id, timestamp)

    def recent_count(self, transaction_id, now, window_seconds=60):
        return self.database.recent_attempt_count(transaction_id, now - window_seconds)


class SafetyKernel:
    """Single deterministic gate for every money-moving write action."""

    def __init__(self, max_transaction=3000, max_quantity=3, max_discount=300, max_attempts_per_minute=5, duplicate_checker=None, rate_limiter=None):
        self.max_transaction = max_transaction
        self.max_quantity = max_quantity
        self.max_discount = max_discount
        self.max_attempts_per_minute = max_attempts_per_minute
        self.duplicate_checker = duplicate_checker or (lambda transaction_id: False)
        self.rate_limiter = rate_limiter or InMemoryRateLimiter()

    def check_payment(self, *, transaction_id, items, requested_amount, authorized_amount=None, confirmed=False, discount=0):
        catalog = {item["sku"]: item for item in items}
        quantities = defaultdict(int)
        for item in items:
            quantities[item["sku"]] += int(item.get("quantity", 0))
        recalculated_amount = sum(
            int(product.get("price_inr", 0)) * quantity
            for sku, quantity in quantities.items()
            if (product := catalog.get(sku))
        )
        now = datetime.now(timezone.utc).timestamp()
        recent_count = self.rate_limiter.recent_count(transaction_id, now)
        duplicate_exists = self.duplicate_checker(transaction_id)
        checks = [
            {"check_name": "AUTHORIZATION_CHECK", "passed": confirmed and authorized_amount == requested_amount, "reason": "Explicit approval matches the requested amount." if confirmed and authorized_amount == requested_amount else "Explicit approval for this exact amount is required."},
            {"check_name": "AMOUNT_CHECK", "passed": bool(quantities) and requested_amount > 0 and recalculated_amount == requested_amount, "reason": "Requested amount matches the backend-recalculated cart total." if quantities and requested_amount > 0 and recalculated_amount == requested_amount else f"Backend total is ₹{recalculated_amount}; a non-empty cart and exact positive amount are required."},
            {"check_name": "TRANSACTION_LIMIT_CHECK", "passed": requested_amount <= self.max_transaction, "reason": f"Amount is within ₹{self.max_transaction}." if requested_amount <= self.max_transaction else f"Amount exceeds the ₹{self.max_transaction} limit."},
            {"check_name": "QUANTITY_CHECK", "passed": sum(quantities.values()) <= self.max_quantity, "reason": f"Quantity is within {self.max_quantity} item(s)." if sum(quantities.values()) <= self.max_quantity else f"Quantity exceeds the {self.max_quantity}-item limit."},
            {"check_name": "DISCOUNT_CHECK", "passed": 0 <= discount <= self.max_discount, "reason": f"Discount is within ₹{self.max_discount}." if 0 <= discount <= self.max_discount else f"Discount exceeds the ₹{self.max_discount} limit."},
            {"check_name": "RATE_LIMIT_CHECK", "passed": recent_count < self.max_attempts_per_minute, "reason": "Session payment-attempt rate is within policy." if recent_count < self.max_attempts_per_minute else "Too many payment attempts in the last minute."},
            {"check_name": "DUPLICATE_CHECK", "passed": not duplicate_exists, "reason": "No successful payment has been recorded for this transaction." if not duplicate_exists else "A successful payment already exists for this transaction."},
        ]
        allowed = all(check["passed"] for check in checks)
        # Record every attempt, not just successful ones — otherwise someone
        # hammering the endpoint with mismatched amounts (failing
        # AMOUNT_CHECK every time) never trips RATE_LIMIT_CHECK.
        self.rate_limiter.record(transaction_id, now)
        failed = next((check for check in checks if not check["passed"]), None)
        return {
            "allowed": allowed,
            "ruleViolated": failed["check_name"] if failed else None,
            "reason": failed["reason"] if failed else "All seven Safety Kernel checks passed.",
            "suggestedAction": "Review the cart and authorization." if failed else "Proceed to Razorpay TEST MODE or DEMO MODE.",
            "checks": checks,
            "recalculated_amount": recalculated_amount,
        }