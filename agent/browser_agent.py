"""Thin Playwright wrapper that drives a real, visible browser against the
CartMind storefront. Selectors for the storefront pages are our own (stable,
data-* attributes). Selectors inside the Razorpay Checkout iframe were
captured live against the actual TEST MODE checkout and may need small
adjustments if Razorpay changes their UI.

The Razorpay-checkout functions below are module-level (operate on a `page`,
not a class) so both BrowserAgent (used by agent.py, one long-lived headed
browser) and cli.py (a fresh headless page per invocation) share exactly one
implementation instead of two copies drifting apart.
"""
import time

from playwright.sync_api import sync_playwright


def rzp_frame(page):
    for frame in page.frames:
        if "razorpay" in frame.url:
            return frame
    return None


def safe_click(page, locator):
    """Never raises — a click that fails even with a force fallback usually
    means the target vanished from under us (an overlay auto-dismissed,
    a re-render swapped it out), which the caller should treat the same as
    'nothing to click' rather than a fatal error."""
    try:
        locator.click(timeout=4000)
        return True
    except Exception:
        pass
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        locator.click(timeout=4000, force=True)
        return True
    except Exception:
        return False


def type_verified(page, frame, selector, value, attempts=3):
    """Types into a field and confirms the full value actually landed.
    The Razorpay card form re-renders/reformats as you type (auto-inserted
    spaces, mask libraries), which can silently drop keystrokes typed too
    early or too fast — so verify by reading the committed value back
    rather than trusting that type() succeeding means the value stuck."""
    expected_digits = "".join(ch for ch in value if ch.isalnum())
    for attempt in range(attempts):
        element = frame.query_selector(selector)
        if not element or not element.is_visible():
            page.wait_for_timeout(500 * (attempt + 1))
            continue
        field = frame.locator(selector)
        if not safe_click(page, field):
            page.wait_for_timeout(500 * (attempt + 1))
            continue
        try:
            field.fill("")
            page.wait_for_timeout(150)
            field.type(value, delay=90)
            page.wait_for_timeout(300)
        except Exception:
            page.wait_for_timeout(500 * (attempt + 1))
            continue
        element = frame.query_selector(selector)
        actual = element.input_value() if element else ""
        actual_digits = "".join(ch for ch in actual if ch.isalnum())
        if actual_digits == expected_digits:
            return True
        page.wait_for_timeout(500 * (attempt + 1))
    return False


def click_submit(page, frame, attempts=4):
    target = frame.get_by_test_id("add-card-cta")
    if target.count() == 0:
        target = frame.get_by_text("Continue", exact=True)
    if target.count() == 0:
        return False
    button = target.last if target.count() > 1 else target.first
    for _ in range(attempts):
        try:
            button.click(timeout=5000)
            return True
        except Exception:
            page.wait_for_timeout(800)
    return False


def _modal_has_rendered(page):
    """A "razorpay" frame existing in page.frames is NOT proof the modal
    opened — checkout.js injects a background prefetch iframe on page load,
    before any click. Only trust that content has actually rendered inside
    it (card fields, a contact step, or an OTP step)."""
    frame = rzp_frame(page)
    if not frame:
        return False
    for selector in ('input[name="card.number"]', 'input[name="contact"]', 'input[placeholder*="OTP" i]'):
        el = frame.query_selector(selector)
        if el and el.is_visible():
            return True
    return False


def open_razorpay_checkout(page):
    """Opens the real Razorpay Checkout modal, retrying the click since a
    click can land before the page has finished settling right after a
    goto(), or the click can silently fail to register. Also gives
    checkout.js (loaded from Razorpay's CDN) time to actually finish
    initializing on a cold page load before the first click attempt —
    clicking #pay-button before that script has run does nothing.
    Both the storefront's own backend (remote Postgres round-trips) and
    Razorpay's own modal (its own API calls) have been observed taking much
    longer than usual under network load, so this budgets real patience —
    up to ~45s total — rather than giving up after a few quick retries."""
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if _modal_has_rendered(page):
            return
        try:
            page.click("#pay-button", timeout=4000)
        except Exception:
            pass
        page.wait_for_timeout(2500)


def read_checkout_status(page, poll=False):
    if poll:
        # The handler's own /verify-payment round-trip does its own Postgres
        # writes, which have been observed taking much longer than usual —
        # give this real time rather than declaring "pending" prematurely.
        for _ in range(40):
            status_el = page.query_selector("#checkout-status")
            if status_el and status_el.get_attribute("data-status"):
                break
            page.wait_for_timeout(1000)
    else:
        page.wait_for_timeout(1500)
    status_el = page.query_selector("#checkout-status")
    if not status_el:
        return {"status": "unknown"}
    return {"status": status_el.get_attribute("data-status") or "pending", "text": status_el.inner_text()}


def pay_with_card(page, card_number, expiry, cvv, phone="9876543219", otp="1234"):
    """Types the card visibly into the real Razorpay iframe, handles the
    contact-details step, the card form, an optional RBI 'save card'
    prompt, and an optional OTP step, then returns the final status.
    This is the single source of truth for driving Razorpay Checkout —
    agent.py (BrowserAgent) and cli.py both go through this path."""
    try:
        return _pay_with_card(page, card_number, expiry, cvv, phone, otp)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _pay_with_card(page, card_number, expiry, cvv, phone, otp):
    open_razorpay_checkout(page)
    if not _modal_has_rendered(page):
        return {"error": "Razorpay checkout modal did not render after retrying the pay button."}
    frame = rzp_frame(page)

    # The modal can land on a payment-METHOD picker (Cards / Netbanking /
    # Wallet) instead of the card form directly — _modal_has_rendered only
    # confirms the modal itself opened, not which screen it's on. Click into
    # "Cards" to reveal the actual card-number field before typing into it.
    for _ in range(4):
        if frame.query_selector('input[name="card.number"]'):
            break
        cards_option = frame.get_by_text("Cards", exact=True)
        if cards_option.count() and cards_option.first.is_visible():
            try:
                cards_option.first.click(timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(800)
        else:
            page.wait_for_timeout(600)

    # Razorpay sometimes shows a blocking "contact details" overlay before
    # the card form is interactive, and sometimes shows the card form
    # directly. is_visible() alone can't tell (covered inputs still report
    # visible), so check for the overlay explicitly.
    for _ in range(3):
        overlay = frame.query_selector('[data-testid="contact-overlay-container"]')
        if not overlay or not overlay.is_visible():
            break
        contact_input = frame.query_selector('input[name="contact"]')
        if contact_input:
            type_verified(page, frame, 'input[name="contact"]', phone)
        click_submit(page, frame)
        page.wait_for_timeout(1500)

    # A leftover dropdown/overlay (e.g. the country-code picker) can still be
    # intercepting clicks. Escape clears Razorpay's overlay stack without
    # touching form values.
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    # Wait for the card number field to actually be attached and settled
    # before typing anything — right after the contact/overlay step the
    # iframe can still be re-rendering, which is exactly when a type() call
    # loses characters partway through.
    try:
        frame.locator('input[name="card.number"]').wait_for(state="visible", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(500)

    for selector, value in (
        ('input[name="card.number"]', card_number.replace(" ", "")),
        ('input[name="card.expiry"]', expiry.replace("/", "")),
        ('input[name="card.cvv"]', cvv),
    ):
        type_verified(page, frame, selector, value)

    remaining_contact = frame.query_selector('input[name="contact"]')
    if remaining_contact and remaining_contact.is_visible() and not (remaining_contact.input_value() or ""):
        type_verified(page, frame, 'input[name="contact"]', phone)

    click_submit(page, frame)
    page.wait_for_timeout(2500)

    # RBI tokenisation prompt ("Save your card as per RBI guidelines?") can
    # appear before the OTP step. Decline it so the flow keeps moving.
    maybe_later = frame.get_by_text("Maybe later", exact=True)
    if maybe_later.count() and maybe_later.first.is_visible():
        maybe_later.first.click()
        page.wait_for_timeout(1500)

    otp_input = None
    for _ in range(8):
        otp_input = frame.query_selector('input[placeholder*="OTP" i], input[name*="otp" i]')
        if otp_input and otp_input.is_visible():
            break
        otp_input = None
        page.wait_for_timeout(1000)

    if otp_input:
        type_verified(page, frame, 'input[placeholder*="OTP" i], input[name*="otp" i]', otp)
        click_submit(page, frame)
        page.wait_for_timeout(2500)

    return read_checkout_status(page, poll=True)


def login_or_signup(page, base_url, email, password, name=""):
    """Logs in with the given credentials; if the account doesn't exist yet,
    signs up with the same credentials instead. Returns the resulting mode
    so the caller knows which one happened."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_timeout(800)

    if "/login" not in page.url:
        return {"logged_in": True, "mode": "login"}

    error = page.query_selector(".blocked")
    error_text = error.inner_text() if error else ""

    page.goto(f"{base_url}/signup")
    if name:
        page.fill('input[name="name"]', name)
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_timeout(800)

    if "/signup" not in page.url:
        return {"logged_in": True, "mode": "signup"}

    signup_error = page.query_selector(".blocked")
    return {
        "logged_in": False,
        "error": (signup_error.inner_text() if signup_error else None) or error_text or "Login and signup both failed.",
    }


class BrowserAgent:
    def __init__(self, base_url="http://127.0.0.1:5000", headless=False):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=headless)
        self.page = self.browser.new_page()
        self.base_url = base_url

    def close(self):
        self.browser.close()
        self.pw.stop()

    def search(self, query="", color=None, max_price=None):
        url = f"{self.base_url}/search?q={query}"
        if color:
            url += f"&color={color}"
        if max_price:
            url += f"&max_price={max_price}"
        self.page.goto(url)
        self.page.wait_for_selector(".product-card", timeout=5000) if self._has_results() else None
        cards = self.page.query_selector_all(".product-card")
        return [
            {
                "sku": c.get_attribute("data-product-id"),
                "price_inr": int(c.get_attribute("data-price") or 0),
                "color": c.get_attribute("data-color"),
                "category": c.get_attribute("data-category"),
                "name": c.query_selector("h3").inner_text(),
            }
            for c in cards
        ]

    def _has_results(self):
        return self.page.query_selector(".product-card") is not None

    def open_product(self, sku):
        self.page.goto(f"{self.base_url}/product/{sku}")

    def add_to_cart(self):
        self.page.click('[data-action="add-to-cart"]')

    def go_to_checkout(self):
        self.page.goto(f"{self.base_url}/checkout")
        if "/login" in self.page.url:
            return {"blocked": True, "requires_login": True, "reason": "Not logged in. Call login first, then retry checkout."}
        blocked = self.page.query_selector('[data-checkout-blocked="true"]')
        if blocked:
            return {"blocked": True, "reason": blocked.query_selector("p").inner_text()}
        summary = self.page.query_selector("#checkout-summary")
        return {
            "blocked": False,
            "order_id": summary.get_attribute("data-order-id") if summary else None,
            "amount": int(summary.get_attribute("data-order-amount") or 0) if summary else 0,
        }

    def login(self, email, password, name=""):
        return login_or_signup(self.page, self.base_url, email, password, name)

    def open_razorpay_checkout(self):
        open_razorpay_checkout(self.page)

    def pay_with_card(self, card_number, expiry, cvv, phone="9876543219", otp="1234"):
        return pay_with_card(self.page, card_number, expiry, cvv, phone, otp)

    def read_checkout_status(self, poll=False):
        return read_checkout_status(self.page, poll=poll)
