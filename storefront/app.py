import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import CartMindDatabase
from gating import GatingService
from mandate import IntentMandate
from razorpay_service import RazorpayService
from safety_kernel import SafetyKernel

from flask_sock import Sock

app = Flask(__name__)
app.secret_key = os.getenv("STOREFRONT_SECRET", "cartmind-dev-secret")
app.jinja_env.auto_reload = True  # keep template edits live even with debug=False
sock = Sock(app)

# Live view of the payment automation: the frontend opens a WS with a
# client-generated stream_id before sending the chat message, and
# _run_test_payment (below) pushes CDP screencast frames to any socket
# registered under that id while it drives the real Razorpay iframe. This is
# what lets a HOSTED deployment (headless, no local desktop) still show the
# card being typed live in the browser, instead of only a step-trail after
# the fact.
PAYMENT_STREAMS = {}


@sock.route("/ws/payment-stream/<stream_id>")
def payment_stream(ws, stream_id):
    PAYMENT_STREAMS.setdefault(stream_id, []).append(ws)
    try:
        while True:
            ws.receive(timeout=30)  # None on timeout — just keeps the handler (and socket) alive
    except Exception:
        pass  # client disconnected — ConnectionClosed or similar
    finally:
        if ws in PAYMENT_STREAMS.get(stream_id, []):
            PAYMENT_STREAMS[stream_id].remove(ws)


def _broadcast_frame(stream_id, base64_jpeg):
    for ws in list(PAYMENT_STREAMS.get(stream_id, [])):
        try:
            ws.send(base64_jpeg)
        except Exception:
            try:
                PAYMENT_STREAMS[stream_id].remove(ws)
            except ValueError:
                pass

CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
CATALOG_BY_SKU = {item["sku"]: item for item in CATALOG}

database = CartMindDatabase()
gate = GatingService()
safety_kernel = SafetyKernel(max_transaction=5000, duplicate_checker=database.has_successful_payment)
MANDATE_MAX_ORDER_VALUE = GatingService.MAX_ORDER_VALUE


def get_cart():
    return session.setdefault("cart", {})


def cart_total(cart):
    return sum(CATALOG_BY_SKU[sku]["price_inr"] * qty for sku, qty in cart.items() if sku in CATALOG_BY_SKU)


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return database.get_user_by_id(user_id)


GUEST_EMAIL = "guest@cartmind.local"


def _ensure_user():
    """Checkout/payment shouldn't require an account for this demo — auto-
    provision (and log in as) a shared guest account instead of blocking."""
    user = current_user()
    if user:
        return user
    user = database.get_user_by_email(GUEST_EMAIL)
    if not user:
        user_id = database.create_user(GUEST_EMAIL, generate_password_hash("guest"), "Guest")
        user = database.get_user_by_id(user_id)
    session["user_id"] = user["id"]
    return user


def _singularize(word):
    """Crude plural stripping ('shoes' -> 'shoe') so a plural search term
    still matches catalog tags/names that are singular, without needing a
    real stemming library for this small demo catalog."""
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def filter_catalog(q="", color="", category="", product_type="", max_price=None):
    results = CATALOG
    if q:
        words = q.lower().split()
        results = [
            p for p in results
            if all(
                w in (p["name"] + " " + p.get("description", "") + " " + " ".join(p.get("tags", []))).lower()
                or _singularize(w) in (p["name"] + " " + p.get("description", "") + " " + " ".join(p.get("tags", []))).lower()
                for w in words
            )
        ]
    if color:
        results = [p for p in results if p.get("color", "").lower() == color.lower()]
    if category:
        results = [p for p in results if p.get("category", "").lower() == category.lower()]
    if product_type:
        results = [p for p in results if product_type.lower() in [t.lower() for t in p.get("tags", [])]]
    if max_price:
        results = [p for p in results if p["price_inr"] <= max_price]
    return results


@app.context_processor
def inject_user():
    return {"user": current_user()}


@app.route("/")
def home():
    return redirect(url_for("search"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html", error=None, cart_count=sum(get_cart().values()))

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    name = request.form.get("name", "").strip()

    if not email or not password:
        return render_template("signup.html", error="Email and password are required.", cart_count=sum(get_cart().values()))
    if database.get_user_by_email(email):
        return render_template("signup.html", error="An account with this email already exists.", cart_count=sum(get_cart().values()))

    user_id = database.create_user(email, generate_password_hash(password), name)
    session["user_id"] = user_id
    database.add_event("auth", "signup", "created", 0, {"email": email})
    return redirect(request.args.get("next") or url_for("search"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None, cart_count=sum(get_cart().values()))

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    user = database.get_user_by_email(email)

    if not user or not check_password_hash(user["password_hash"], password):
        database.add_event("auth", "login", "failed", 0, {"email": email})
        return render_template("login.html", error="Invalid email or password.", cart_count=sum(get_cart().values()))

    session["user_id"] = user["id"]
    database.add_event("auth", "login", "success", 0, {"email": email})
    return redirect(request.args.get("next") or url_for("search"))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return redirect(url_for("search"))


@app.route("/profile")
def profile():
    user = current_user()
    if not user:
        return redirect(url_for("login", next=url_for("profile")))
    orders = database.get_orders_for_user(user["id"])
    return render_template("profile.html", user=user, orders=orders, cart_count=sum(get_cart().values()))


@app.route("/search")
def search():
    q = request.args.get("q", "").strip().lower()
    color = request.args.get("color", "").strip().lower()
    category = request.args.get("category", "").strip().lower()
    product_type = request.args.get("type", "").strip().lower()
    max_price = request.args.get("max_price", type=int)

    results = filter_catalog(q, color, category, product_type, max_price)

    return render_template("search.html", products=results, q=q, color=color, category=category, product_type=product_type, max_price=max_price, cart_count=sum(get_cart().values()))


@app.route("/product/<sku>")
def product(sku):
    item = CATALOG_BY_SKU.get(sku)
    if not item:
        return "Product not found", 404
    return render_template("product.html", p=item, cart_count=sum(get_cart().values()))


@app.route("/cart/add/<sku>", methods=["POST"])
def add_to_cart(sku):
    if sku not in CATALOG_BY_SKU:
        return "Unknown product", 404
    cart = get_cart()
    cart[sku] = cart.get(sku, 0) + 1
    session["cart"] = cart
    return redirect(url_for("view_cart"))


@app.route("/cart/remove/<sku>", methods=["POST"])
def remove_from_cart(sku):
    cart = get_cart()
    cart.pop(sku, None)
    session["cart"] = cart
    return redirect(url_for("view_cart"))


@app.route("/cart/clear", methods=["POST"])
def clear_cart():
    session["cart"] = {}
    return redirect(url_for("view_cart"))


@app.route("/cart")
def view_cart():
    cart = get_cart()
    items = [{**CATALOG_BY_SKU[sku], "quantity": qty} for sku, qty in cart.items() if sku in CATALOG_BY_SKU]
    total = cart_total(cart)
    return render_template("cart.html", items=items, total=total, cart_count=sum(cart.values()))


def _run_checkout_gate(user, channel="manual"):
    """Runs the real gating/safety-kernel checks and (if allowed) creates the
    Razorpay order, exactly as the checkout page does. Shared by the /checkout
    route and the chat agent's go_to_checkout tool so both see one source of
    truth for blocked/allowed and the resulting order."""
    cart = get_cart()
    items = [{**CATALOG_BY_SKU[sku], "quantity": qty} for sku, qty in cart.items() if sku in CATALOG_BY_SKU]
    total = cart_total(cart)
    key_id = os.getenv("RAZORPAY_KEY_ID", "")

    if not items:
        return {"items": [], "total": 0, "order": None, "key_id": key_id, "blocked_reason": "Cart is empty."}

    intent = IntentMandate(
        user_id=str(user["id"]),
        merchant_id="merchant_demo",
        amount=total,
        description="Storefront checkout",
        authorized_by=user["email"],
    )

    class _CartView:
        def get_items(self_inner):
            return cart

        def get_total(self_inner, catalog):
            return total

    checkout_mandate = gate.create_cart_mandate(intent, _CartView(), CATALOG)
    gate.confirm_cart(checkout_mandate, "yes, confirm this cart")
    accepted, policy_result = gate.check_cart_against_policy(checkout_mandate)
    database.add_event("checkout", "check_cart_against_policy", "allowed" if accepted else "blocked", total, policy_result)

    if not accepted:
        return {"items": items, "total": total, "order": None, "key_id": key_id, "blocked_reason": policy_result["reason"]}

    kernel = safety_kernel.check_payment(
        transaction_id=f"trx_{request.cookies.get('session', 'anon')}_{total}",
        items=[{**CATALOG_BY_SKU[sku], "sku": sku, "quantity": qty} for sku, qty in cart.items() if sku in CATALOG_BY_SKU],
        requested_amount=total,
        authorized_amount=total,
        confirmed=True,
    )
    database.add_event("checkout", "seven_check_decision", "allowed" if kernel["allowed"] else "blocked", total, kernel)
    if not kernel["allowed"]:
        return {"items": items, "total": total, "order": None, "key_id": key_id, "blocked_reason": kernel["reason"]}

    # Reuse an existing not-yet-paid order for this exact cart total instead
    # of creating a fresh Razorpay order every time /checkout is loaded — the
    # chat shows the user an order ID before asking for card details, then
    # pay_with_test_card re-loads this same route internally; without reuse
    # that second load would silently create and pay a DIFFERENT order than
    # the one the user was shown, making a real capture look like nothing
    # happened.
    existing = next(
        (o for o in database.get_orders_for_user(user["id"]) if o["status"] == "created" and o["amount_inr"] == total),
        None,
    )
    if existing:
        order = {"id": existing["order_id"], "amount": total * 100, "currency": "INR", "status": "created"}
        # Refresh the stored item snapshot (image paths etc. may have
        # changed in the catalog since this order was first created) so a
        # reused order doesn't permanently freeze stale product data.
        database.update_payment_status(order["id"], "created", details={"items": items, "channel": channel})
    else:
        service = RazorpayService(key_id=key_id or None, key_secret=os.getenv("RAZORPAY_KEY_SECRET") or None)
        order = service.create_order({"amount": total * 100, "currency": "INR", "receipt": f"storefront_{total}"})
        database.add_event("checkout", "create_order", order.get("status", "unknown"), total, {**order, "items": items, "channel": channel})
        auth_mode = "razorpay_test_auth" if not service.use_simulator else "local_simulator"
        database.add_payment(order, total, auth_mode, details={**order, "items": items, "channel": channel}, transaction_id=order.get("id"), user_id=user["id"])

    return {"items": items, "total": total, "order": order, "key_id": key_id, "blocked_reason": None}


@app.route("/checkout")
def checkout():
    user = _ensure_user()
    channel = "agent" if request.headers.get("X-CartMind-Channel") == "agent" else "manual"
    result = _run_checkout_gate(user, channel=channel)
    return render_template("checkout.html", **result)


@app.route("/order-confirmed")
def order_confirmed():
    order_id = request.args.get("order_id", "")
    amount = request.args.get("amount", type=int) or 0
    payment = database.get_payment_by_order_id(order_id) if order_id else None
    items = (payment["details"].get("items") if payment else None) or []
    return render_template("order_confirmed.html", order_id=order_id, amount=amount, items=items, cart_count=sum(get_cart().values()))


@app.route("/order-failed")
def order_failed():
    reason = request.args.get("reason", "The payment could not be completed.")
    return render_template("order_failed.html", reason=reason, cart_count=sum(get_cart().values()))


@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    payload = request.get_json(force=True)
    order_id = payload.get("razorpay_order_id", "")
    payment_id = payload.get("razorpay_payment_id", "")
    signature = payload.get("razorpay_signature", "")

    service = RazorpayService()
    verified = service.verify_payment_signature(order_id, payment_id, signature)
    if verified:
        database.update_payment_status(order_id, "captured", {"payment_id": payment_id, "reason": "Signature verified."})
        database.add_event("checkout", "payment_captured", "captured", 0, {"order_id": order_id, "payment_id": payment_id})
        session["cart"] = {}
        return jsonify({"success": True, "status": "captured"})

    database.update_payment_status(order_id, "failed", {"reason": "Signature verification failed."})
    database.add_event("checkout", "payment_verification", "failed", 0, {"order_id": order_id})
    return jsonify({"success": False, "error": "Signature verification failed."}), 400


@app.route("/payment-failed", methods=["POST"])
def payment_failed():
    payload = request.get_json(force=True)
    order_id = payload.get("order_id", "")
    reason = payload.get("reason", "Checkout closed or declined by the customer.")
    database.update_payment_status(order_id, "failed", {"reason": reason})
    database.add_event("checkout", "payment_failed", "failed", 0, {"order_id": order_id, "reason": reason})
    return jsonify({"success": True, "status": "failed"})


AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Search/narrow the catalog by free-text query, color, product type (dress/shirt/shoe), or max price. Call again with just a color/type to narrow an existing result set.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text search, e.g. 'dress'. Leave empty when only narrowing."},
                    "color": {"type": "string"},
                    "type": {"type": "string", "description": "One of: dress, shirt, shoe."},
                    "max_price": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_product",
            "description": "Open a specific product's page by SKU to view its full details. Call this before add_to_cart so the user sees the product page first, the way a real shopper would.",
            "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a specific product (by SKU) to the cart. Call view_product for that SKU first so its page is shown before adding.",
            "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_cart",
            "description": "Remove everything from the cart. Only call this after the user explicitly asks to clear/empty their cart.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "go_to_checkout",
            "description": "Take the user to checkout. Only call this after the user explicitly says they want to check out or pay. If the result has requires_login=true, ask the user for an email and password (or use ones they already gave you) and call login_or_signup, then call go_to_checkout again.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "login_or_signup",
            "description": "Log the user into their account with an email and password. If no account exists yet with that email, one is created automatically with the same credentials — you do not need to ask the user to sign up separately, just get an email and password and call this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "password": {"type": "string"},
                    "name": {"type": "string", "description": "Optional display name, used only if a new account is created."},
                },
                "required": ["email", "password"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pay_with_test_card",
            "description": "Open the real Razorpay TEST MODE checkout and submit a card, completing payment. Only call this after go_to_checkout has succeeded (blocked=false) and the user has explicitly given card_number, expiry, and cvv in this conversation — never call it on a bare 'pay'/'yes' without those values present.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_number": {"type": "string"},
                    "expiry": {"type": "string", "description": "MM/YY"},
                    "cvv": {"type": "string"},
                    "cardholder_name": {"type": "string", "description": "Optional; only used for display, not required by Razorpay TEST MODE."},
                },
                "required": ["card_number", "expiry", "cvv"],
            },
        },
    },
]

DEFAULT_CARD = {"card_number": "5267318187975449", "expiry": "12/28", "cvv": "123"}
KNOWN_BAD_CARDS = {"4111111111111111"}

AGENT_SYSTEM_PROMPT = """You are CartMind's shopping assistant, embedded directly in the storefront the user is browsing right now.
This chat renders as a narrow message bubble that only supports plain paragraphs, bullet lists (- item), and **bold**
— it does NOT render markdown tables. NEVER use a table (no | pipes, no |---|---| separator rows). When listing
multiple products, always use a bullet list instead, one line per product, e.g.:
- **Aster Heels** (SHOE-201) — Black — ₹1,299
Always call search_catalog immediately on the user's first request, even a broad one (e.g. "I want a dress" →
search_catalog(query="dress") right away, showing whatever the catalog has, THEN ask if they'd like to narrow by
color/price). Never ask clarifying questions before searching at least once — an initial shortlist plus a follow-up
question is far more useful than a question with no results shown yet. Narrow further conversationally as the user
gives more detail (e.g. "black ones" → search_catalog(query="dress", color="black")).
Never call add_to_cart, clear_cart, go_to_checkout, or pay_with_test_card without the user explicitly telling you to do so in this turn.
When the user says to add a specific product to their cart, ALWAYS call view_product for that SKU first (so its page
shows before anything is added, like a real shopper would), then call add_to_cart in the same turn.
No login is required to check out or pay — go_to_checkout works immediately, don't ask for or require an account. Only
use login_or_signup if the user explicitly asks to create an account or log in themselves.

Once go_to_checkout succeeds (blocked=false) and the user says they want to pay, ALWAYS ask for payment details before
calling pay_with_test_card — never assume or silently fill in a default card just because the user said "pay" or "yes".
Ask in one message, formatted as a short labeled list, e.g.:

  To complete payment, please share:
  - Card number:
  - Expiry (MM/YY):
  - CVV:
  - Name on card (optional):

This is a TEST MODE demo storefront — no real card or money is involved, so it's fine to collect these directly in
chat. If the user says they don't have one or asks for a test card, THEN offer this known-working one:
5267318187975449, expiry 12/28, CVV 123. Only call pay_with_test_card once the user has actually supplied card_number,
expiry, and cvv in the conversation (their own values, or the offered test card if they accepted it) — do not use
4111111111111111 or other generic test numbers, Razorpay's India TEST MODE rejects those as "international card not
supported". Report the final status (captured or failed) back to the user plainly.
Keep replies short and concrete: what you found (name, price, SKU), what you're about to do, and why."""


def agent_dispatch(name, tool_input, stream_id=None):
    if name == "search_catalog":
        results = filter_catalog(
            q=tool_input.get("query", ""),
            color=tool_input.get("color", ""),
            product_type=tool_input.get("type", ""),
            max_price=tool_input.get("max_price"),
        )
        products = [{"sku": p["sku"], "name": p["name"], "price_inr": p["price_inr"], "color": p.get("color", "")} for p in results[:8]]
        navigate = f"/search?q={tool_input.get('query', '')}&color={tool_input.get('color', '')}&type={tool_input.get('type', '')}"
        return {"count": len(results), "products": products}, navigate

    if name == "view_product":
        sku = tool_input.get("sku", "")
        item = CATALOG_BY_SKU.get(sku)
        if not item:
            return {"error": f"Unknown SKU {sku}"}, None
        details = {"sku": item["sku"], "name": item["name"], "price_inr": item["price_inr"], "color": item.get("color", ""), "description": item.get("description", "")}
        return details, f"/product/{sku}"

    if name == "add_to_cart":
        sku = tool_input.get("sku", "")
        if sku not in CATALOG_BY_SKU:
            return {"error": f"Unknown SKU {sku}"}, None
        cart = get_cart()
        cart[sku] = cart.get(sku, 0) + 1
        session["cart"] = cart
        return {"added": True, "sku": sku, "cart_count": sum(cart.values())}, "/cart"

    if name == "clear_cart":
        session["cart"] = {}
        return {"cleared": True, "cart_count": 0}, None

    if name == "go_to_checkout":
        user = _ensure_user()
        result = _run_checkout_gate(user, channel="agent")
        if result["blocked_reason"]:
            return {"blocked": True, "reason": result["blocked_reason"]}, "/checkout"
        return {"blocked": False, "order_id": result["order"]["id"], "amount_inr": result["total"]}, "/checkout"

    if name == "login_or_signup":
        email = tool_input.get("email", "").strip().lower()
        password = tool_input.get("password", "")
        name_field = tool_input.get("name", "").strip()
        if not email or not password:
            return {"error": "email and password are required"}, None
        return _run_visible_login(email, password, name_field), None

    if name == "pay_with_test_card":
        card_number = (tool_input.get("card_number") or DEFAULT_CARD["card_number"]).replace(" ", "")
        if card_number in KNOWN_BAD_CARDS:
            card_number = DEFAULT_CARD["card_number"]
        expiry = tool_input.get("expiry") or DEFAULT_CARD["expiry"]
        cvv = tool_input.get("cvv") or DEFAULT_CARD["cvv"]
        result = _run_test_payment(card_number, expiry, cvv, stream_id=stream_id)
        if isinstance(result, dict) and result.get("status") == "captured":
            session["cart"] = {}
            result["cart_count"] = 0
            result["payment_status"] = "captured"
            return result, f"/order-confirmed?order_id={result.get('order_id', '')}&amount={result.get('amount_inr', 0)}"
        if isinstance(result, dict):
            result["payment_status"] = "failed"
            reason = result.get("reason") or result.get("error") or f"Status: {result.get('status', 'unknown')}"
            return result, f"/order-failed?reason={reason}"
        return result, None

    return {"error": f"Unknown tool {name}"}, None


CDP_URL = os.getenv("CARTMIND_CDP_URL", "http://127.0.0.1:9222")
# Render (and most cloud hosts) set RENDER automatically; there's no local
# desktop there for a visible/maximized Chromium window to attach to or draw
# on, so force headless in that case. Locally this stays False so the
# maximized-popup fallback (and the CDP-attach path) keep working as before.
_ON_CLOUD_HOST = bool(os.getenv("RENDER") or os.getenv("CARTMIND_FORCE_HEADLESS"))


@contextmanager
def _browser_page():
    """Yields a real Playwright page to drive, preferring the user's own
    already-running browser over the Chrome DevTools Protocol (CARTMIND_CDP_URL
    / http://127.0.0.1:9222 — launch Chrome/Edge with
    --remote-debugging-port=9222 to enable this), so automation types into the
    SAME tab the user is already looking at instead of a separate popup.
    Falls back to a fresh, maximized, foregrounded Chromium window (sharing
    the session cookie) if no such browser is reachable. Never closes a
    browser it doesn't own."""
    from playwright.sync_api import sync_playwright

    cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
    base_url = request.host_url.rstrip("/")
    session_cookie = request.cookies.get(cookie_name)

    with sync_playwright() as pw:
        if _ON_CLOUD_HOST:
            browser = pw.chromium.launch(headless=True)
            owns_browser = True
        else:
            try:
                browser = pw.chromium.connect_over_cdp(CDP_URL)
                owns_browser = False
            except Exception:
                browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
                owns_browser = True

        if owns_browser:
            context = browser.new_context(no_viewport=True)
            if session_cookie:
                context.add_cookies([{"name": cookie_name, "value": session_cookie, "url": base_url}])
            page = context.new_page()
        else:
            # Always open a NEW tab in the user's existing browser window —
            # same window, so it's visible, but never the exact tab the chat
            # widget's own fetch() is running from. Navigating that tab out
            # from under itself would kill the JS context waiting to render
            # the reply, so the confirmation would never show up.
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            if session_cookie:
                context.add_cookies([{"name": cookie_name, "value": session_cookie, "url": base_url}])
            page = context.new_page()

        try:
            # Tags every request this page makes to the storefront as
            # agent-driven, so /checkout can attribute the resulting payment
            # to the chat agent rather than a manual click — purely for the
            # owner console's "manual vs agent" breakdown.
            context.set_extra_http_headers({"X-CartMind-Channel": "agent"})
            page.bring_to_front()
            yield page, base_url
        finally:
            if owns_browser:
                browser.close()
            else:
                # The confirmation/toast renders in the tab that made this
                # chat request, not this automation tab — bring that other
                # tab back to front so the user naturally lands back on it
                # instead of staring at this one after it closes.
                for other_context in browser.contexts:
                    for p in other_context.pages:
                        if p is not page and p.url.startswith(base_url):
                            try:
                                p.bring_to_front()
                            except Exception:
                                pass
                            break
                page.close()


def _run_test_payment(card_number, expiry, cvv, stream_id=None):
    """Drives the real Razorpay TEST MODE checkout in the user's own browser.
    Returns a "steps" trail alongside the result so the chat can show what
    actually happened even when the automation's own browser window isn't
    visible/in focus on the user's screen. If stream_id is given, also pushes
    a live CDP screencast to any /ws/payment-stream/<stream_id> socket, which
    is how a headless/hosted deployment can still show the card being typed
    in real time in the browser instead of only a step-trail afterward."""
    import browser_agent

    steps = ["Opened the checkout page"]
    with _browser_page() as (page, base_url):
        cdp = None
        if stream_id:
            try:
                cdp = page.context.new_cdp_session(page)
                cdp.on("Page.screencastFrame", lambda params: (
                    _broadcast_frame(stream_id, params["data"]),
                    cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}),
                ))
                cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 60, "maxWidth": 960, "maxHeight": 720, "everyNthFrame": 1})
            except Exception:
                cdp = None
        try:
            return _drive_checkout(page, base_url, card_number, expiry, cvv, steps)
        finally:
            if cdp:
                try:
                    cdp.send("Page.stopScreencast")
                except Exception:
                    pass


def _drive_checkout(page, base_url, card_number, expiry, cvv, steps):
    import browser_agent

    # /checkout does several sequential Postgres round-trips (Neon, over
    # the network) plus a live Razorpay order-creation API call before it
    # can respond — this has been observed taking 15-20s on its own, so
    # give it real headroom instead of the default 30s "load" wait
    # (which would also wait on the external checkout.js script tag).
    page.goto(f"{base_url}/checkout", timeout=45000, wait_until="domcontentloaded")
    if "/login" in page.url:
        return {"error": "Not logged in.", "blocked": True, "requires_login": True, "steps": steps}
    blocked = page.query_selector('[data-checkout-blocked="true"]')
    if blocked:
        steps.append("Checkout was blocked before payment could start")
        return {"blocked": True, "reason": blocked.query_selector("p").inner_text(), "steps": steps}
    steps.append("Order created — opening the real Razorpay checkout modal")
    summary = page.query_selector("#checkout-summary")
    order_id = summary.get_attribute("data-order-id") if summary else None
    order_amount = int(summary.get_attribute("data-order-amount") or 0) if summary else 0
    result = browser_agent.pay_with_card(page, card_number, expiry, cvv)
    result = dict(result)
    result["order_id"] = order_id
    result["amount_inr"] = order_amount // 100
    error = result.get("error")
    status = result.get("status")
    if error and "did not render" in error:
        # Failed before any typing happened — don't claim steps that
        # never occurred.
        steps.append(f"Error: {error}")
    else:
        steps.append("Typed the card number, expiry, and CVV into Razorpay's form")
        steps.append("Submitted the card and handled any contact/OTP/save-card prompts")
        if status:
            steps.append(f"Final status: {status}")
        elif error:
            steps.append(f"Error: {error}")
    result["steps"] = steps
    return result


def _run_visible_login(email, password, name_field):
    """Drives the real /login (falling back to /signup) page in the user's
    own browser, then returns to the search page — visible, just like
    payment, instead of silently writing the session server-side. Also
    mirrors the resulting login into this request's own Flask session so
    later tool calls in the same chat turn (e.g. go_to_checkout right after)
    see the user as logged in immediately, without waiting for the browser's
    new cookie to reach the next request."""
    import browser_agent

    with _browser_page() as (page, base_url):
        result = browser_agent.login_or_signup(page, base_url, email, password, name_field)
        page.goto(f"{base_url}/search")

    if result.get("logged_in"):
        user = database.get_user_by_email(email)
        if user:
            session["user_id"] = user["id"]
            database.add_event("auth", result.get("mode", "login"), "success", 0, {"email": email, "via": "agent"})
    return result


CHAT_MODELS = ["openai/gpt-oss-20b"]


def _create_chat_completion(client, messages, tool_choice):
    """Tries each model in CHAT_MODELS in order, falling through to the next
    one only on a rate-limit error (each Groq model has its own separate
    daily token quota, so gpt-oss-120b running out doesn't mean gpt-oss-20b
    has too) — any other error is raised immediately rather than masked."""
    last_exc = None
    for model in CHAT_MODELS:
        try:
            return client.chat.completions.create(
                model=model,
                max_tokens=800,
                tools=AGENT_TOOLS,
                tool_choice=tool_choice,
                messages=messages,
            )
        except Exception as exc:
            last_exc = exc
            if "rate_limit" in str(exc).lower() or "429" in str(exc):
                continue
            raise
    raise last_exc


@app.route("/agent/transcribe", methods=["POST"])
def agent_transcribe():
    """Speech-to-text for the chat widget's mic button. Reuses the same
    Groq Whisper model the CLI agent's voice-input path already uses, so
    there's one transcription behavior across both surfaces."""
    if not os.getenv("GROQ_API_KEY"):
        return jsonify({"error": "Voice input is unavailable: GROQ_API_KEY is not configured."}), 503

    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "audio file is required"}), 400

    from groq import Groq

    client = Groq()
    try:
        result = client.audio.transcriptions.create(
            file=(audio_file.filename or "recording.webm", audio_file.read()),
            model="whisper-large-v3-turbo",
            response_format="json",
            temperature=0,
        )
    except Exception as exc:
        return jsonify({"error": f"Transcription failed: {exc}"}), 502

    return jsonify({"text": result.text.strip()})


@app.route("/agent/chat", methods=["POST"])
def agent_chat():
    if not os.getenv("GROQ_API_KEY"):
        return jsonify({"reply": "Voice/chat assistant is unavailable: GROQ_API_KEY is not configured.", "navigate": None, "cart_count": None}), 503

    from groq import Groq

    payload = request.get_json(force=True)
    user_message = payload.get("message", "").strip()
    history = payload.get("history", [])
    stream_id = payload.get("stream_id")
    if not user_message:
        return jsonify({"error": "message is required"}), 400

    client = Groq()
    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_message}]

    # These small Groq models will sometimes just say "payment captured" (or
    # let the client's canned "opening payment window" text stand in) as
    # plain text without ever actually calling pay_with_test_card — either
    # when card details are given directly, or when the user just confirms
    # ("yes") a card the assistant already proposed earlier in the
    # conversation. In either case, force this round to call a tool rather
    # than trust the model's own judgment about whether to call it.
    CARD_DIGITS_RE = re.compile(r"\d[\d ]{11,18}\d")
    CONFIRM_RE = re.compile(r"\b(yes|yep|yeah|confirm|go ahead|proceed|do it|sure|pay now)\b", re.I)

    def _recent_history_has_card(msgs, lookback=6):
        for m in msgs[-lookback:]:
            content = m.get("content")
            if isinstance(content, str) and CARD_DIGITS_RE.search(content):
                return True
        return False

    looks_like_card_details = bool(CARD_DIGITS_RE.search(user_message))
    confirming_pending_card = bool(CONFIRM_RE.search(user_message)) and _recent_history_has_card(history)
    force_payment_tool = looks_like_card_details or confirming_pending_card

    navigate = None
    cart_count = None
    reply_text = ""
    payment_tool_called = False
    payment_steps = None
    payment_status = None

    for round_num in range(4):
        tool_choice = "auto"
        if round_num == 0 and force_payment_tool:
            tool_choice = {"type": "function", "function": {"name": "pay_with_test_card"}}
        try:
            response = _create_chat_completion(client, messages, tool_choice)
        except Exception as exc:
            # A forced tool_choice can be hard-rejected in several distinct
            # ways — the model wanting a different function, or wanting to
            # answer in plain text instead of calling anything at all.
            # pay_with_test_card already re-runs the checkout gate
            # internally, so it's always safe to just retry this round with
            # tool_choice="auto" instead of failing the whole turn.
            if tool_choice != "auto":
                try:
                    response = _create_chat_completion(client, messages, "auto")
                except Exception as exc2:
                    return jsonify({"reply": f"Assistant error: {exc2}", "navigate": None, "cart_count": None}), 502
            else:
                return jsonify({"reply": f"Assistant error: {exc}", "navigate": None, "cart_count": None}), 502

        message = response.choices[0].message
        messages.append(message.model_dump(exclude_unset=True, exclude_none=True))

        if message.content:
            reply_text = message.content

        if not message.tool_calls:
            break

        for call in message.tool_calls:
            tool_input = json.loads(call.function.arguments or "{}")
            if call.function.name == "pay_with_test_card":
                payment_tool_called = True
            result, nav = agent_dispatch(call.function.name, tool_input, stream_id=stream_id)
            if nav is not None:
                navigate = nav  # last tool call that actually requests a navigation wins
            if isinstance(result, dict) and "cart_count" in result:
                cart_count = result["cart_count"]
            if isinstance(result, dict) and "steps" in result:
                payment_steps = result["steps"]
            if isinstance(result, dict) and "payment_status" in result:
                payment_status = result["payment_status"]
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})

    # Never let a hallucinated "payment captured" reach the user if the payment
    # tool was never actually invoked this turn.
    if force_payment_tool and not payment_tool_called:
        reply_text = "Something went wrong submitting that — I wasn't able to actually process the payment. Could you resend the card details?"
        messages.append({"role": "assistant", "content": reply_text})

    # Always append the real step trail when payment ran, regardless of what
    # the model chose to say — the automation's own browser window may not be
    # visible/in focus, so this is the user's only reliable confirmation of
    # what actually happened.
    if payment_steps:
        reply_text = (reply_text + "\n\n" if reply_text else "") + "Steps taken:\n" + "\n".join(f"- {s}" for s in payment_steps)

    # pay_with_test_card always sets its own explicit navigate (to
    # /order-confirmed or /order-failed) regardless of outcome, which — via
    # the "last non-null navigate wins" rule above — already overrides any
    # leftover nav from an earlier go_to_checkout call in the same turn. The
    # client only follows navigate AFTER already rendering the reply and
    # toast, so redirecting here never blows away what the user just saw.

    new_history = messages[1:]  # drop the system prompt before sending back to the client
    return jsonify({
        "reply": reply_text,
        "navigate": navigate,
        "cart_count": cart_count,
        "history": new_history,
        "payment_status": payment_status,
    })


@app.route("/trail")
def trail():
    return jsonify(database.snapshot())


def _demand_signal(stock, sold):
    """Deterministic, rule-based demand signal — same explainability pattern as gating.py:
    a plain-English reason, not a hidden model score."""
    if stock <= 0:
        return {
            "signal": "reorder",
            "action": "Reorder now",
            "reason": "Out of stock" + (f" while {sold} unit(s) have already sold." if sold else "."),
        }
    if sold >= 3 and stock / sold < 1.5:
        return {
            "signal": "reorder",
            "action": "Reorder soon",
            "reason": f"{sold} sold against only {stock} left — selling faster than stock covers.",
        }
    if stock < 5:
        return {
            "signal": "watch",
            "action": "Monitor stock",
            "reason": f"Only {stock} unit(s) left; a few more sales would exhaust it.",
        }
    if sold == 0:
        return {
            "signal": "slow",
            "action": "Consider a promotion",
            "reason": "No captured sales yet against current stock.",
        }
    return {
        "signal": "steady",
        "action": "No action needed",
        "reason": f"{sold} sold, {stock} in stock — comfortable cover.",
    }


def _match_events(events, payment):
    matched = []
    for event in events:
        details = event.get("details") or {}
        if payment.get("transaction_id") and details.get("transaction_id") == payment["transaction_id"]:
            matched.append(event)
        elif payment.get("order_id") and details.get("id") == payment["order_id"]:
            matched.append(event)
        elif payment.get("order_id") and details.get("order_id") == payment["order_id"]:
            matched.append(event)
    return sorted(matched, key=lambda e: e["id"])


@app.route("/owner", methods=["GET", "POST"])
def owner():
    owner_password = os.getenv("OWNER_PASSWORD", "owner123")

    if request.method == "POST":
        if request.form.get("password", "") == owner_password:
            session["is_owner"] = True
        else:
            return render_template("owner_login.html", error="Incorrect owner password.")
        return redirect(url_for("owner"))

    if not session.get("is_owner"):
        return render_template("owner_login.html", error=None)

    snap = database.snapshot()
    payments = snap["payments"]
    events = snap["events"]
    stats = database.payment_stats()
    all_sku_sales = database.sku_sales()
    sold_by_sku = {row["sku"]: row["quantity"] for row in all_sku_sales}
    sku_sales = all_sku_sales[:8]
    blocked = database.blocked_events(10)

    SIGNAL_RANK = {"reorder": 0, "watch": 1, "slow": 2, "steady": 3}
    demand = []
    for p in CATALOG:
        sold = sold_by_sku.get(p["sku"], 0)
        info = _demand_signal(p.get("stock", 0), sold)
        demand.append({"sku": p["sku"], "name": p["name"], "stock": p.get("stock", 0), "sold": sold, **info})
    demand.sort(key=lambda row: (SIGNAL_RANK.get(row["signal"], 9), -row["sold"]))
    low_stock = [row for row in demand if row["signal"] == "reorder"]

    SIGNAL_ICONS = {"reorder": "&#9888;", "watch": "&#128064;", "slow": "&#128200;", "steady": "&#10003;"}
    max_stock = max((row["stock"] for row in demand), default=1) or 1
    for row in demand:
        row["stock_pct"] = round(row["stock"] / max_stock * 100)
        row["icon"] = SIGNAL_ICONS.get(row["signal"], "")
    demand_summary = {key: sum(1 for row in demand if row["signal"] == key) for key in SIGNAL_RANK}

    SUCCESS = ("paid", "captured", "success")
    volume = sum(p["amount_inr"] for p in payments if p["status"] in SUCCESS)

    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc).date()
    days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    by_day = {d.isoformat(): 0 for d in days}
    for p in payments:
        if p["status"] not in SUCCESS:
            continue
        day = str(p.get("created_at", ""))[:10]
        if day in by_day:
            by_day[day] += p["amount_inr"]
    volume_series = [{"label": d.strftime("%d/%m"), "value": by_day[d.isoformat()]} for d in days]
    max_volume = max([v["value"] for v in volume_series] or [1], default=1) or 1

    status_counts = {}
    for p in payments:
        status_counts[p["status"]] = status_counts.get(p["status"], 0) + 1
    max_status = max(status_counts.values() or [1], default=1) or 1

    STATUS_COLORS = {
        "paid": "#067d62", "captured": "#067d62", "success": "#067d62",
        "failed": "#b12704", "created": "#c45500", "awaiting_checkout": "#c45500",
    }
    import math
    radius, circumference = 52, 2 * math.pi * 52
    total_payments = sum(status_counts.values()) or 1
    donut_segments = []
    offset = 0.0
    for status, n in sorted(status_counts.items(), key=lambda kv: -kv[1]):
        pct = n / total_payments
        length = pct * circumference
        donut_segments.append({
            "status": status, "n": n, "pct": round(pct * 100, 1),
            "color": STATUS_COLORS.get(status, "#565959"),
            "dasharray": f"{length:.2f} {circumference - length:.2f}",
            "offset": round(-offset, 2),
        })
        offset += length

    CATEGORY_PALETTE = ["#ff8a3d", "#131921", "#3d7bff", "#0aab7c", "#c45500", "#9061e8"]
    category_revenue = {}
    for row in all_sku_sales:
        cat = CATALOG_BY_SKU.get(row["sku"], {}).get("category", "other")
        category_revenue[cat] = category_revenue.get(cat, 0) + row["revenue_inr"]
    category_total = sum(category_revenue.values()) or 1
    category_segments = []
    cat_offset = 0.0
    for i, (cat, rev) in enumerate(sorted(category_revenue.items(), key=lambda kv: -kv[1])):
        pct = rev / category_total
        length = pct * circumference
        category_segments.append({
            "category": cat, "revenue": rev, "pct": round(pct * 100, 1),
            "color": CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)],
            "dasharray": f"{length:.2f} {circumference - length:.2f}",
            "offset": round(-cat_offset, 2),
        })
        cat_offset += length

    action_status = {(r["action"], r["status"]): r["n"] for r in database.audit_action_status_counts()}
    stage_attempts = sum(n for (a, s), n in action_status.items() if a == "check_cart_against_policy")
    stage_cart_ok = action_status.get(("check_cart_against_policy", "allowed"), 0)
    stage_kernel_ok = action_status.get(("seven_check_decision", "allowed"), 0)
    stage_captured = action_status.get(("payment_captured", "captured"), 0)
    funnel = [
        {"label": "Checkout attempts", "n": stage_attempts},
        {"label": "Passed cart policy", "n": stage_cart_ok},
        {"label": "Passed Safety Kernel", "n": stage_kernel_ok},
        {"label": "Payment captured", "n": stage_captured},
    ]
    max_funnel = funnel[0]["n"] or 1
    for stage in funnel:
        stage["pct"] = round(stage["n"] / max_funnel * 100) if max_funnel else 0

    FUNNEL_COLORS = ["#131921", "#3d4a63", "#ff8a3d", "#0aab7c"]
    funnel_h = 220 / len(funnel)
    min_w = 40
    for i, stage in enumerate(funnel):
        top_w = 300 if i == 0 else max(min_w, (funnel[i - 1]["pct"] / 100) * 300)
        bottom_w = max(min_w, (stage["pct"] / 100) * 300)
        y_top, y_bottom = i * funnel_h, (i + 1) * funnel_h
        tl, tr = (175 - top_w / 2, y_top), (175 + top_w / 2, y_top)
        br, bl = (175 + bottom_w / 2, y_bottom), (175 - bottom_w / 2, y_bottom)
        stage["points"] = f"{tl[0]:.1f},{tl[1]:.1f} {tr[0]:.1f},{tr[1]:.1f} {br[0]:.1f},{br[1]:.1f} {bl[0]:.1f},{bl[1]:.1f}"
        stage["label_y"] = round((y_top + y_bottom) / 2 + 5, 1)
        stage["color"] = FUNNEL_COLORS[i % len(FUNNEL_COLORS)]
    funnel_height = round(220 / len(funnel) * len(funnel) + 25)

    policy_cap = safety_kernel.max_transaction
    avg_order = round(volume / stats["successful"]) if stats["successful"] else 0
    gauge_pct = min(100, round(avg_order / policy_cap * 100)) if policy_cap else 0
    gauge_arc = math.pi * 80
    needle_angle_rad = math.pi - (gauge_pct / 100 * math.pi)
    needle_x = round(100 - 62 * math.cos(needle_angle_rad), 1)
    needle_y = round(100 - 62 * math.sin(needle_angle_rad), 1)

    line_points = []
    for i, point in enumerate(volume_series):
        x = i * (350 / max(1, len(volume_series) - 1))
        y = 120 - round(point["value"] / max_volume * 95)
        line_points.append((round(x, 1), y))
    line_path = " ".join(f"{x},{y}" for x, y in line_points)
    area_path = f"M {line_points[0][0]},120 L " + " L ".join(f"{x},{y}" for x, y in line_points) + f" L {line_points[-1][0]},120 Z"

    users_count = database.count_users()

    channel_raw = database.channel_counts()
    CHANNEL_COLORS = {"manual": "#131921", "agent": "#ff8a3d"}
    CHANNEL_LABELS = {"manual": "Manual checkout", "agent": "Chat agent"}
    channel_total = sum(c["total"] for c in channel_raw.values()) or 1
    channel_segments = []
    ch_offset = 0.0
    for key in ("manual", "agent"):
        n = channel_raw[key]["total"]
        pct = n / channel_total
        length = pct * circumference
        channel_segments.append({
            "key": key, "label": CHANNEL_LABELS[key], "n": n, "captured": channel_raw[key]["captured"],
            "pct": round(pct * 100, 1), "color": CHANNEL_COLORS[key],
            "dasharray": f"{length:.2f} {circumference - length:.2f}",
            "offset": round(-ch_offset, 2),
        })
        ch_offset += length

    watch_items = [row for row in demand if row["signal"] == "watch"]
    slow_items = [row for row in demand if row["signal"] == "slow"]
    recent_blocks = database.recent_blocked_count(60)
    recent_failed = database.recent_event_count(minutes=60, action="payment_failed")

    alerts = []
    if low_stock:
        names = ", ".join(row["name"] for row in low_stock[:3])
        alerts.append({
            "severity": "critical", "icon": "&#9888;",
            "title": f"{len(low_stock)} product(s) need reordering",
            "detail": f"{names}{'…' if len(low_stock) > 3 else ''} — out of stock, or selling faster than remaining stock covers.",
        })
    if recent_blocks >= 3:
        alerts.append({
            "severity": "warning", "icon": "&#128683;",
            "title": f"{recent_blocks} blocked payment attempts in the last hour",
            "detail": "Review mandate limits, catalog policy, or whether this is expected traffic.",
        })
    if recent_failed >= 3:
        alerts.append({
            "severity": "warning", "icon": "&#9889;",
            "title": f"{recent_failed} failed payments in the last hour",
            "detail": "Cards declining or checkout being abandoned more than usual — worth a look at the ledger below.",
        })
    if watch_items:
        names = ", ".join(row["name"] for row in watch_items[:3])
        alerts.append({
            "severity": "info", "icon": "&#128064;",
            "title": f"{len(watch_items)} product(s) running low",
            "detail": f"{names}{'…' if len(watch_items) > 3 else ''} — not urgent yet, but worth watching.",
        })
    if len(slow_items) >= 5:
        alerts.append({
            "severity": "info", "icon": "&#128200;",
            "title": f"{len(slow_items)} product(s) with no captured sales",
            "detail": "Consider a promotion, bundle, or markdown — see the demand table for the full list.",
        })

    def _item_summary(payment):
        items = (payment.get("details") or {}).get("items", [])
        if not items:
            return ""
        parts = [f"{item.get('name', item.get('sku', '?'))} × {item.get('quantity', 1)}" for item in items]
        return ", ".join(parts)

    def _display_time(iso_str):
        try:
            dt = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            return iso_str or "—"
        return dt.strftime("%d %b, %I:%M %p")

    ledger = [
        {
            "payment": p,
            "trail": _match_events(events, p),
            "item_summary": _item_summary(p),
            "created_display": _display_time(p.get("created_at")),
        }
        for p in payments
    ]

    return render_template(
        "owner.html",
        stats=stats,
        volume=volume,
        ledger=ledger,
        sku_sales=sku_sales,
        blocked=blocked,
        demand=demand,
        alerts=alerts,
        volume_series=volume_series,
        max_volume=max_volume,
        status_counts=sorted(status_counts.items(), key=lambda kv: -kv[1]),
        max_status=max_status,
        donut_segments=donut_segments,
        total_payments=total_payments,
        category_segments=category_segments,
        funnel=funnel,
        funnel_height=funnel_height,
        needle_x=needle_x,
        needle_y=needle_y,
        gauge_pct=gauge_pct,
        gauge_arc=round(gauge_arc, 2),
        avg_order=avg_order,
        policy_cap=policy_cap,
        line_path=line_path,
        area_path=area_path,
        line_points=line_points,
        volume_labels=[p["label"] for p in volume_series],
        users_count=users_count,
        channel_segments=channel_segments,
        channel_total=channel_total,
        demand_summary=demand_summary,
    )


@app.route("/owner/logout", methods=["POST"])
def owner_logout():
    session.pop("is_owner", None)
    return redirect(url_for("owner"))


@app.errorhandler(500)
def internal_error(exc):
    app.logger.exception(exc)
    return render_template("error.html", cart_count=sum(get_cart().values())), 500


@app.errorhandler(404)
def not_found(exc):
    return render_template("error.html", not_found=True, cart_count=sum(get_cart().values())), 404


def _launch_debug_browser():
    """Starts the user's own Chrome/Edge with remote debugging enabled and
    points it at the storefront, so _browser_page's CDP connect always finds
    a real window to drive — the chat agent's card-typing then happens right
    in this one browser instead of a separate popup. This makes that the
    default experience of `python app.py` alone, not something that only
    works if you'd separately launched a debug-enabled browser yourself.
    Skips launching if something is already listening on the CDP port
    (e.g. you started your own debug browser, or this is a second run)."""
    import socket
    import subprocess
    import tempfile

    try:
        with socket.create_connection(("127.0.0.1", 9222), timeout=0.3):
            return  # already have a CDP-reachable browser — reuse it
    except OSError:
        pass

    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    exe = next((c for c in candidates if c.is_file()), None)
    if not exe:
        return  # no known browser found — _browser_page will fall back to its own Playwright-launched window

    profile_dir = Path(tempfile.gettempdir()) / "cartmind-debug-browser"
    try:
        subprocess.Popen([
            str(exe),
            "--remote-debugging-port=9222",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--start-maximized",
            "http://127.0.0.1:5000/search",
        ], close_fds=True)
    except OSError:
        pass


if __name__ == "__main__":
    import threading

    print("CartMind storefront running at http://127.0.0.1:5000/search")
    # Delayed so the browser navigates only after the Flask server below is
    # actually accepting connections, instead of hitting a dead port.
    # With the reloader on, this module runs once in the watcher process and
    # again in the actual server subprocess (WERKZEUG_RUN_MAIN=true) — only
    # the latter should try opening a browser, otherwise it fires twice.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.2, _launch_debug_browser).start()
    app.run(port=5000, debug=False, use_reloader=True, threaded=True)
