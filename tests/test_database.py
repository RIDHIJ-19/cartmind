import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import CartMindDatabase


def make_db(tmp_path):
    return CartMindDatabase(path=tmp_path / "test.db")


def test_creates_schema_and_survives_reinit(tmp_path):
    db_path = tmp_path / "test.db"
    CartMindDatabase(path=db_path)
    CartMindDatabase(path=db_path)  # re-running init/migrations must not raise


def test_add_and_fetch_user(tmp_path):
    db = make_db(tmp_path)
    user_id = db.create_user("a@example.com", "hashed", "Alice")
    user = db.get_user_by_id(user_id)
    assert user["email"] == "a@example.com"
    assert db.get_user_by_email("a@example.com")["id"] == user_id


def test_payment_attempt_rate_window(tmp_path):
    db = make_db(tmp_path)
    now = time.time()
    db.record_payment_attempt("trx1", now - 100)  # outside 60s window
    db.record_payment_attempt("trx1", now - 10)   # inside window
    assert db.recent_attempt_count("trx1", now - 60) == 1


def test_payment_stats_and_duplicate_check(tmp_path):
    db = make_db(tmp_path)
    order = {"id": "order_1", "entity": "order", "status": "paid", "currency": "INR"}
    db.add_payment(order, 1000, "local_simulator", transaction_id="trx_a")
    assert db.has_successful_payment("trx_a") is True
    assert db.has_successful_payment("trx_missing") is False
    stats = db.payment_stats()
    assert stats["successful"] == 1
