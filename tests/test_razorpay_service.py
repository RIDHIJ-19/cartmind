import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from razorpay_service import LiveKeyRejectedError, RazorpayService


def test_rejects_live_key_id():
    with pytest.raises(LiveKeyRejectedError):
        RazorpayService(key_id="rzp_live_abc123", key_secret="whatever")


def test_uses_simulator_when_no_keys_configured(monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    service = RazorpayService()
    assert service.use_simulator is True


def test_simulated_order_succeeds_for_positive_amount():
    service = RazorpayService(key_id=None, key_secret=None)
    order = service.create_order({"amount": 1000, "currency": "INR"})
    assert order["status"] == "paid"
    assert order["id"].startswith("order_sim_")


def test_simulated_order_respects_force_fail():
    service = RazorpayService(key_id=None, key_secret=None)
    order = service.create_order({"amount": 1000, "currency": "INR", "force_fail": True})
    assert order["status"] == "failed"


def test_simulated_order_ids_are_unique():
    service = RazorpayService(key_id=None, key_secret=None)
    ids = {service.create_order({"amount": 1000})["id"] for _ in range(20)}
    assert len(ids) == 20


def test_capture_payment_simulated_success():
    service = RazorpayService(key_id=None, key_secret=None)
    result = service.capture_payment("order_sim_abc")
    assert result["status"] == "captured"
    assert result["order_id"] == "order_sim_abc"


def test_capture_payment_simulated_force_fail():
    service = RazorpayService(key_id=None, key_secret=None)
    result = service.capture_payment("order_sim_abc", {"force_fail": True})
    assert result["status"] == "failed"


def test_verify_payment_signature_false_in_simulator_mode():
    service = RazorpayService(key_id=None, key_secret=None)
    assert service.verify_payment_signature("order_1", "pay_1", "sig") is False
