"""Single-shot CLI driver for the CartMind browser agent.

Each invocation launches a fresh headless browser, but session state (the
Flask cart cookie) is persisted to session_state.json between calls via
Playwright's storage_state, so a sequence of separate CLI calls behaves like
one continuous shopping session. A screenshot is saved after every action so
a caller with no live browser view can still see what happened.

Usage:
    python agent/cli.py search "dress" [--color black] [--max-price 3000]
    python agent/cli.py select DRESS-106
    python agent/cli.py add-to-cart
    python agent/cli.py checkout
    python agent/cli.py pay 5267318187975449 12/28 123
    python agent/cli.py reset
"""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_agent import pay_with_card

AGENT_DIR = Path(__file__).resolve().parent
STATE_FILE = AGENT_DIR / "session_state.json"
SCREENSHOT_FILE = AGENT_DIR / "last_screenshot.png"
BASE_URL = "http://127.0.0.1:5000"


def _load_context(pw, browser):
    if STATE_FILE.exists():
        return browser.new_context(storage_state=str(STATE_FILE))
    return browser.new_context()


def _save_context(context):
    context.storage_state(path=str(STATE_FILE))


def _screenshot(page):
    page.screenshot(path=str(SCREENSHOT_FILE))


def cmd_search(page, args):
    url = f"{BASE_URL}/search?q={args.query or ''}"
    if args.color:
        url += f"&color={args.color}"
    if args.max_price:
        url += f"&max_price={args.max_price}"
    page.goto(url)
    cards = page.query_selector_all(".product-card")
    results = [
        {
            "sku": c.get_attribute("data-product-id"),
            "price_inr": int(c.get_attribute("data-price") or 0),
            "color": c.get_attribute("data-color"),
            "category": c.get_attribute("data-category"),
            "name": c.query_selector("h3").inner_text(),
        }
        for c in cards
    ]
    return {"count": len(results), "products": results[:8]}


def cmd_select(page, args):
    page.goto(f"{BASE_URL}/product/{args.sku}")
    return {"opened": args.sku}


def cmd_add_to_cart(page, args):
    page.goto(f"{BASE_URL}/product/{args.sku}")
    page.click('[data-action="add-to-cart"]')
    return {"added": True, "sku": args.sku}


def cmd_checkout(page, args):
    page.goto(f"{BASE_URL}/checkout")
    blocked = page.query_selector('[data-checkout-blocked="true"]')
    if blocked:
        return {"blocked": True, "reason": blocked.query_selector("p").inner_text()}
    summary = page.query_selector("#checkout-summary")
    return {
        "blocked": False,
        "order_id": summary.get_attribute("data-order-id") if summary else None,
        "amount_paise": int(summary.get_attribute("data-order-amount") or 0) if summary else 0,
    }


def cmd_pay(page, args):
    page.goto(f"{BASE_URL}/checkout")
    result = pay_with_card(page, args.card_number, args.expiry, args.cvv, phone=args.phone, otp=args.otp)
    if args.screenshot_steps:
        page.screenshot(path=str(AGENT_DIR / "step_card_filled.png"))
    return result


def cmd_reset(page, args):
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    return {"reset": True}


COMMANDS = {
    "search": cmd_search,
    "select": cmd_select,
    "add-to-cart": cmd_add_to_cart,
    "checkout": cmd_checkout,
    "pay": cmd_pay,
    "reset": cmd_reset,
}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--color")
    p.add_argument("--max-price", dest="max_price", type=int)

    p = sub.add_parser("select")
    p.add_argument("sku")

    p = sub.add_parser("add-to-cart")
    p.add_argument("sku")

    sub.add_parser("checkout")

    p = sub.add_parser("pay")
    p.add_argument("card_number")
    p.add_argument("expiry")
    p.add_argument("cvv")
    p.add_argument("--phone", default="9876543219")
    p.add_argument("--otp", default="1234")
    p.add_argument("--screenshot-steps", action="store_true", dest="screenshot_steps")

    sub.add_parser("reset")

    args = parser.parse_args()

    if args.command == "reset":
        result = cmd_reset(None, args)
        print(json.dumps(result))
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = _load_context(pw, browser)
        page = context.new_page()
        try:
            result = COMMANDS[args.command](page, args)
        except Exception as exc:
            result = {"error": str(exc)}
        _screenshot(page)
        _save_context(context)
        browser.close()

    print(json.dumps(result))


if __name__ == "__main__":
    main()
