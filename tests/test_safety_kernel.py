import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safety_kernel import InMemoryRateLimiter, SafetyKernel

ITEM = {"sku": "SKU-1", "price_inr": 1000, "quantity": 1}


def make_kernel(**kwargs):
    defaults = dict(max_transaction=3000, max_quantity=3, max_discount=300, max_attempts_per_minute=5)
    defaults.update(kwargs)
    return SafetyKernel(**defaults)


def test_allows_matching_confirmed_amount():
    kernel = make_kernel()
    result = kernel.check_payment(
        transaction_id="t1",
        items=[ITEM],
        requested_amount=1000,
        authorized_amount=1000,
        confirmed=True,
    )
    assert result["allowed"] is True
    assert result["ruleViolated"] is None


def test_blocks_unconfirmed_payment():
    kernel = make_kernel()
    result = kernel.check_payment(
        transaction_id="t2",
        items=[ITEM],
        requested_amount=1000,
        authorized_amount=1000,
        confirmed=False,
    )
    assert result["allowed"] is False
    assert result["ruleViolated"] == "AUTHORIZATION_CHECK"


def test_blocks_amount_mismatch_against_recalculated_total():
    kernel = make_kernel()
    result = kernel.check_payment(
        transaction_id="t3",
        items=[ITEM],
        requested_amount=999,
        authorized_amount=999,
        confirmed=True,
    )
    assert result["allowed"] is False
    assert result["ruleViolated"] == "AMOUNT_CHECK"
    assert result["recalculated_amount"] == 1000


def test_blocks_over_transaction_limit():
    kernel = make_kernel()
    items = [{"sku": "SKU-1", "price_inr": 5000, "quantity": 1}]
    result = kernel.check_payment(
        transaction_id="t4",
        items=items,
        requested_amount=5000,
        authorized_amount=5000,
        confirmed=True,
    )
    assert result["allowed"] is False
    assert result["ruleViolated"] == "TRANSACTION_LIMIT_CHECK"


def test_blocks_over_quantity_limit():
    kernel = make_kernel()
    items = [{"sku": "SKU-1", "price_inr": 100, "quantity": 10}]
    result = kernel.check_payment(
        transaction_id="t5",
        items=items,
        requested_amount=1000,
        authorized_amount=1000,
        confirmed=True,
    )
    assert result["allowed"] is False
    assert result["ruleViolated"] == "QUANTITY_CHECK"


def test_blocks_duplicate_transaction():
    kernel = make_kernel(duplicate_checker=lambda transaction_id: True)
    result = kernel.check_payment(
        transaction_id="t6",
        items=[ITEM],
        requested_amount=1000,
        authorized_amount=1000,
        confirmed=True,
    )
    assert result["allowed"] is False
    assert result["ruleViolated"] == "DUPLICATE_CHECK"


def test_rate_limit_counts_failed_attempts_too():
    """Regression test: attempts must be counted even when a check other than
    the rate limit fails, otherwise spamming mismatched amounts never trips
    the rate limiter."""
    kernel = make_kernel(max_attempts_per_minute=2)
    for _ in range(2):
        result = kernel.check_payment(
            transaction_id="t7",
            items=[ITEM],
            requested_amount=999,  # deliberately wrong, fails AMOUNT_CHECK
            authorized_amount=999,
            confirmed=True,
        )
        assert result["ruleViolated"] == "AMOUNT_CHECK"

    result = kernel.check_payment(
        transaction_id="t7",
        items=[ITEM],
        requested_amount=1000,
        authorized_amount=1000,
        confirmed=True,
    )
    assert result["allowed"] is False
    assert result["ruleViolated"] == "RATE_LIMIT_CHECK"


def test_rate_limit_is_per_transaction_id():
    kernel = make_kernel(max_attempts_per_minute=1)
    kernel.check_payment(transaction_id="a", items=[ITEM], requested_amount=1000, authorized_amount=1000, confirmed=True)
    result = kernel.check_payment(transaction_id="b", items=[ITEM], requested_amount=1000, authorized_amount=1000, confirmed=True)
    assert result["allowed"] is True


def test_in_memory_rate_limiter_prunes_old_entries():
    limiter = InMemoryRateLimiter()
    limiter.record("x", 0.0)
    assert limiter.recent_count("x", now=1000.0, window_seconds=60) == 0
    assert limiter.attempts["x"] == []
