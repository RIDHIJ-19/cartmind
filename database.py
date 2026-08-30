import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent / "cartmind.db"


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CartMindDatabase:
    def __init__(self, path=DATABASE_PATH, database_url=None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.use_postgres = bool(self.database_url and self.database_url.startswith(("postgres://", "postgresql://")))
        self.path = str(path)
        self._initialize()

    def _connect(self):
        if self.use_postgres:
            try:
                import psycopg

                connection = psycopg.connect(self.database_url)
                connection.row_factory = psycopg.rows.dict_row
                return connection
            except ImportError as exc:
                raise RuntimeError("DATABASE_URL is set but psycopg is not installed.") from exc
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            sqlite_schema = """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    amount_inr INTEGER NOT NULL DEFAULT 0,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    order_id TEXT,
                    payment_id TEXT,
                    status TEXT NOT NULL,
                    amount_inr INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    auth_mode TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT ''
                );
                """
            postgres_schema = """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    amount_inr INTEGER NOT NULL DEFAULT 0,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS payments (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    order_id TEXT,
                    payment_id TEXT,
                    status TEXT NOT NULL,
                    amount_inr INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    auth_mode TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT ''
                );
                """
            if self.use_postgres:
                with connection.cursor() as cursor:
                    for statement in postgres_schema.split(";"):
                        if statement.strip():
                            cursor.execute(statement)
            else:
                connection.executescript(sqlite_schema)

        # Each ALTER runs in its own connection/transaction: in Postgres, one
        # statement failing (e.g. "column already exists") poisons the whole
        # transaction, silently rolling back everything else run alongside
        # it — including unrelated CREATE TABLE statements above, if they
        # shared a connection with a failing ALTER.
        for statement in (
            "ALTER TABLE payments ADD COLUMN transaction_id TEXT",
            "ALTER TABLE payments ADD COLUMN user_id INTEGER",
        ):
            try:
                with self._connect() as connection:
                    connection.execute(statement)
            except Exception:
                pass

    def add_event(self, event_type, action, status, amount_inr=0, details=None):
        with self._connect() as connection:
            sql = """
                INSERT INTO audit_events
                    (created_at, event_type, action, status, amount_inr, details_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """.replace("?", "%s") if self.use_postgres else """
                INSERT INTO audit_events
                    (created_at, event_type, action, status, amount_inr, details_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """
            connection.execute(sql, (_now_iso(), event_type, action, status, int(amount_inr), json.dumps(details or {})))

    def add_payment(self, payment, amount_inr, auth_mode, details=None, transaction_id=None, user_id=None):
        with self._connect() as connection:
            sql = """
                INSERT INTO payments
                    (created_at, order_id, payment_id, status, amount_inr, currency, auth_mode, details_json, transaction_id, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """.replace("?", "%s") if self.use_postgres else """
                INSERT INTO payments
                    (created_at, order_id, payment_id, status, amount_inr, currency, auth_mode, details_json, transaction_id, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            connection.execute(sql, (
                    _now_iso(),
                    payment.get("id") if payment.get("entity") == "order" else payment.get("order_id"),
                    payment.get("id") if payment.get("entity") == "payment" else None,
                    payment.get("status", "unknown"),
                    int(amount_inr),
                    payment.get("currency", "INR"),
                    auth_mode,
                    json.dumps(details or payment),
                    transaction_id,
                    user_id,
                ))

    def create_user(self, email, password_hash, name=""):
        with self._connect() as connection:
            sql = "INSERT INTO users (created_at, email, password_hash, name) VALUES (?, ?, ?, ?)"
            if self.use_postgres:
                sql = sql.replace("?", "%s") + " RETURNING id"
                cursor = connection.execute(sql, (_now_iso(), email, password_hash, name))
                return cursor.fetchone()["id"]
            cursor = connection.execute(sql, (_now_iso(), email, password_hash, name))
            return cursor.lastrowid

    def get_user_by_email(self, email):
        with self._connect() as connection:
            sql = "SELECT * FROM users WHERE email = ?" if not self.use_postgres else "SELECT * FROM users WHERE email = %s"
            row = connection.execute(sql, (email,)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id):
        with self._connect() as connection:
            sql = "SELECT * FROM users WHERE id = ?" if not self.use_postgres else "SELECT * FROM users WHERE id = %s"
            row = connection.execute(sql, (user_id,)).fetchone()
        return dict(row) if row else None

    def get_orders_for_user(self, user_id):
        with self._connect() as connection:
            sql = "SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC" if not self.use_postgres else "SELECT * FROM payments WHERE user_id = %s ORDER BY id DESC"
            rows = [dict(row) for row in connection.execute(sql, (user_id,))]
        for row in rows:
            row["details"] = json.loads(row.pop("details_json"))
        return rows

    def get_payment_by_order_id(self, order_id):
        with self._connect() as connection:
            sql = "SELECT * FROM payments WHERE order_id = ? ORDER BY id DESC LIMIT 1" if not self.use_postgres else "SELECT * FROM payments WHERE order_id = %s ORDER BY id DESC LIMIT 1"
            row = connection.execute(sql, (order_id,)).fetchone()
        if not row:
            return None
        row = dict(row)
        row["details"] = json.loads(row.pop("details_json"))
        return row

    def update_payment_status(self, order_id, status, details=None):
        """Merges `details` into the payment's existing details_json rather
        than replacing it, so fields set at order-creation time (item names,
        channel) survive later status transitions like capture/failure."""
        with self._connect() as connection:
            if details is not None:
                select_sql = "SELECT details_json FROM payments WHERE order_id = ?"
                update_sql = "UPDATE payments SET status = ?, details_json = ? WHERE order_id = ?"
                if self.use_postgres:
                    select_sql = select_sql.replace("?", "%s")
                    update_sql = update_sql.replace("?", "%s")
                row = connection.execute(select_sql, (order_id,)).fetchone()
                existing = json.loads(dict(row)["details_json"]) if row else {}
                merged = {**existing, **details}
                connection.execute(update_sql, (status, json.dumps(merged), order_id))
            else:
                sql = "UPDATE payments SET status = ? WHERE order_id = ?"
                if self.use_postgres:
                    sql = sql.replace("?", "%s")
                connection.execute(sql, (status, order_id))

    def payment_stats(self):
        with self._connect() as connection:
            sql = "SELECT status, COUNT(*) as n FROM payments GROUP BY status"
            rows = [dict(row) for row in connection.execute(sql)]
        total = sum(row["n"] for row in rows)
        successful = sum(row["n"] for row in rows if row["status"] in ("paid", "captured", "success"))
        failed = sum(row["n"] for row in rows if row["status"] == "failed")
        pending = total - successful - failed
        success_rate = round((successful / total) * 100, 1) if total else 0.0
        return {
            "initiated": total,
            "successful": successful,
            "failed": failed,
            "pending": pending,
            "success_rate": success_rate,
        }

    def has_successful_payment(self, transaction_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM payments WHERE transaction_id = ? AND status IN ('paid', 'captured', 'success') LIMIT 1" if not self.use_postgres else "SELECT 1 FROM payments WHERE transaction_id = %s AND status IN ('paid', 'captured', 'success') LIMIT 1",
                (transaction_id,),
            ).fetchone()
        return row is not None

    def sku_sales(self):
        with self._connect() as connection:
            events = [dict(row) for row in connection.execute("SELECT * FROM audit_events WHERE action = 'create_order'")]
            payments = [dict(row) for row in connection.execute("SELECT order_id, status FROM payments")]
        status_by_order = {p["order_id"]: p["status"] for p in payments}
        totals = {}
        for event in events:
            details = json.loads(event["details_json"])
            if status_by_order.get(details.get("id")) not in ("paid", "captured", "success"):
                continue
            for item in details.get("items", []):
                sku = item.get("sku")
                if not sku:
                    continue
                entry = totals.setdefault(sku, {"sku": sku, "name": item.get("name", sku), "quantity": 0, "revenue_inr": 0})
                entry["quantity"] += int(item.get("quantity", 0))
                entry["revenue_inr"] += int(item.get("price_inr", 0)) * int(item.get("quantity", 0))
        return sorted(totals.values(), key=lambda row: -row["revenue_inr"])

    def blocked_events(self, limit=15):
        with self._connect() as connection:
            sql = "SELECT * FROM audit_events WHERE status = 'blocked' ORDER BY id DESC LIMIT ?" if not self.use_postgres else "SELECT * FROM audit_events WHERE status = 'blocked' ORDER BY id DESC LIMIT %s"
            rows = [dict(row) for row in connection.execute(sql, (limit,))]
        for row in rows:
            row["details"] = json.loads(row.pop("details_json"))
        return rows

    def recent_blocked_count(self, minutes=60):
        return self.recent_event_count(minutes=minutes, status="blocked")

    def recent_event_count(self, minutes=60, action=None, status=None):
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        clauses, params = [], []
        if action:
            clauses.append("action = ?")
            params.append(action)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT created_at FROM audit_events{where} ORDER BY id DESC LIMIT 200"
        if self.use_postgres:
            sql = sql.replace("?", "%s")
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(sql, tuple(params))]
        count = 0
        for row in rows:
            try:
                stamp = datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if stamp >= cutoff:
                count += 1
        return count

    def channel_counts(self):
        """How many payments were initiated manually (clicked through the
        storefront) vs by the in-page chat agent, plus how many of each
        actually captured — read from the 'channel' tag stamped on each
        payment's details_json. Rows from before that tag existed default
        to 'manual'."""
        with self._connect() as connection:
            rows = [dict(r) for r in connection.execute("SELECT status, details_json FROM payments")]
        counts = {"manual": {"total": 0, "captured": 0}, "agent": {"total": 0, "captured": 0}}
        for row in rows:
            details = json.loads(row["details_json"])
            channel = details.get("channel", "manual")
            if channel not in counts:
                channel = "manual"
            counts[channel]["total"] += 1
            if row["status"] in ("paid", "captured", "success"):
                counts[channel]["captured"] += 1
        return counts

    def count_users(self):
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) as n FROM users").fetchone()
        return dict(row)["n"]

    def audit_action_status_counts(self):
        with self._connect() as connection:
            rows = [dict(r) for r in connection.execute(
                "SELECT action, status, COUNT(*) as n FROM audit_events GROUP BY action, status"
            )]
        return rows

    def snapshot(self):
        with self._connect() as connection:
            events = [dict(row) for row in connection.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT 50")]
            payments = [dict(row) for row in connection.execute("SELECT * FROM payments ORDER BY id DESC LIMIT 20")]
        for row in events + payments:
            row["details"] = json.loads(row.pop("details_json"))
        return {"events": events, "payments": payments}