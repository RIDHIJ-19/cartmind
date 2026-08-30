# CartMind — Agentic Commerce Demo (Track 01: AI Growth & Agentic Commerce)

## 1. Elevator pitch

You talk to an agent: *"I want a dress."* It searches a live storefront (yours — a
dummy Amazon-style site), narrows results with you turn by turn ("show me red
ones" → "pick B"), adds the item to the cart, walks through Razorpay
test-mode checkout, and **types the test card number into the real form
live**, character by character. Every money-moving action passes through a
deterministic gate before it executes — bounded, explainable, auditable — and
you demo one gate rejection live to prove it isn't just theater.

Split-screen demo: left = chat with the agent, right = real browser window
the agent is driving on your dummy storefront.

---

## 2. Demo script (what the judges see)

1. **You type/speak**: "I want a dress under ₹3000."
2. **Right pane**: browser navigates to `/search?q=dress`, agent reads the
   DOM, chat replies with a shortlist of ~10 items.
3. **You**: "Red ones only."
4. **Right pane**: browser clicks the color filter live. Chat narrows to 2.
5. **You**: "The second one."
6. **Right pane**: browser opens the product page, clicks **Add to Cart**,
   proceeds to checkout.
7. **Gate check #1** (silent, logged): cart total vs. mandate cap — passes.
8. **Agent**: "Want me to add the matching belt for ₹800? It's within
   budget." **You**: "No thanks, just checkout."
9. **Right pane**: agent types into the Razorpay checkout form live —
   card number, expiry, CVV — using Playwright's real keystroke typing
   (visibly character-by-character, like watching someone type).
10. **Gate check #2**: final amount vs. mandate cap, explicit confirmation
    on file — passes, payment fires via Razorpay **test mode**.
11. **Failure demo (required by the brief)**: you ask the agent to also buy
    a second item that would push the order over the mandate cap. Agent
    replies *"Skipping that — would put the order at ₹5,400, over your
    ₹5,000 limit"* and the audit trail shows the rejected attempt with a
    reason, not a silent drop or a crash.
12. **Left pane**: flash the audit trail (`render_trail()` output or a
    simple `/trail` page) showing every step: quote → confirmation →
    gate-pass → gate-reject → payment → capture.

That's the whole pitch in under 3 minutes.

---

## 3. Architecture

```
 ┌─────────────┐        chat/voice         ┌──────────────────┐
 │   You (chat) │ ───────────────────────▶ │   agent.py         │
 └─────────────┘ ◀─────────────────────── │  (conversation loop)│
                                            └─────────┬─────────┘
                                                       │ tool calls
                                       ┌───────────────┼────────────────┐
                                       ▼                                ▼
                              ┌─────────────────┐            ┌──────────────────┐
                              │ browser_agent.py │            │   gating.py        │
                              │ (Playwright,     │◀──checks──▶│ (mandate + rules) │
                              │  drives real      │           └──────────────────┘
                              │  browser window)  │                      │
                              └────────┬──────────┘                      ▼
                                       │ real clicks/typing        ┌──────────────┐
                                       ▼                            │ database.py  │
                          ┌─────────────────────────┐               │ (audit trail)│
                          │  Dummy storefront (Flask) │              └──────────────┘
                          │  /search /product /cart   │
                          │  /checkout → Razorpay      │
                          └───────────┬───────────────┘
                                       │ test-mode API
                                       ▼
                              ┌────────────────┐
                              │ Razorpay (test) │
                              └────────────────┘
```

Two separate processes, both driven from `agent.py`:
- The **conversation loop** decides *what* to do next (search / filter /
  select / checkout / propose upsell).
- The **browser agent** is a thin Playwright wrapper that actually *does* it
  in a visible browser window — this is what makes the right-hand pane real
  instead of simulated.

---

## 4. Folder structure

```
cartmind-demo/
├── storefront/                  # your dummy "Amazon"
│   ├── app.py                   # Flask app
│   ├── catalog.json             # product data
│   ├── templates/
│   │   ├── search.html
│   │   ├── product.html
│   │   ├── cart.html
│   │   └── checkout.html
│   └── static/style.css
│
├── agent/
│   ├── agent.py                 # conversation loop (LLM tool-calling)
│   ├── browser_agent.py         # Playwright driver
│   ├── gating.py                # mandate + rule checks
│   ├── mandate.py                # mandate dataclass
│   ├── database.py               # SQLite audit trail
│   └── razorpay_service.py       # Razorpay order/verify wrapper
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## 5. Tech stack

- **Storefront**: Flask (fast to scaffold, plain Jinja templates, real DOM
  with predictable selectors)
- **Agent brain**: Claude or GPT via API, tool-calling (function-calling)
  mode — the LLM picks a tool, your code executes it, result goes back in
  context
- **Browser automation**: Playwright (Python), **headed** (visible) browser
  window so it's screen-shareable
- **Payments**: `razorpay` Python SDK, **test mode only**
- **DB**: SQLite (no hosting needed for a 2-day build)

Install:
```bash
pip install flask playwright razorpay anthropic python-dotenv
playwright install chromium
```

---

## 6. Storefront: make it agent-friendly on purpose

Since you own this site, don't hide structure from your own agent — expose it.

`catalog.json`:
```json
[
  {
    "id": "d001",
    "name": "Red Wrap Dress",
    "category": "dresses",
    "color": "red",
    "price": 2499,
    "image": "/static/img/d001.jpg"
  },
  {
    "id": "d002",
    "name": "Blue Summer Dress",
    "category": "dresses",
    "color": "blue",
    "price": 1899,
    "image": "/static/img/d002.jpg"
  }
]
```

`templates/search.html` — give every product card stable, semantic
attributes the agent can read reliably instead of guessing from visual
layout:
```html
<div class="product-card"
     data-product-id="{{ p.id }}"
     data-price="{{ p.price }}"
     data-color="{{ p.color }}"
     data-category="{{ p.category }}">
  <img src="{{ p.image }}">
  <h3>{{ p.name }}</h3>
  <p>₹{{ p.price }}</p>
  <a href="/product/{{ p.id }}" class="view-btn">View</a>
</div>
```

Routes to build in `storefront/app.py`:
- `GET /search?q=&color=&max_price=` — filterable listing
- `GET /product/<id>` — detail page, `Add to Cart` button with
  `data-action="add-to-cart"`
- `GET /cart` — shows current cart (session-based is fine)
- `GET /checkout` — renders a **Razorpay Checkout** embed (test mode) —
  this is the real form the agent will type into
- `POST /verify-payment` — verifies signature, marks order paid

Keep it to these four pages. Don't build user accounts, reviews, or a real
catalog — none of that helps the demo.

---

## 7. Browser agent (`browser_agent.py`)

Thin wrapper exposing agent-callable actions. Use `type()` with a delay so
keystrokes are visibly typed, not instantly pasted — this is the "codex-style"
visual effect you want:

```python
from playwright.sync_api import sync_playwright

class BrowserAgent:
    def __init__(self, base_url="http://127.0.0.1:5000"):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=False)
        self.page = self.browser.new_page()
        self.base_url = base_url

    def search(self, query, color=None, max_price=None):
        url = f"{self.base_url}/search?q={query}"
        if color: url += f"&color={color}"
        if max_price: url += f"&max_price={max_price}"
        self.page.goto(url)
        cards = self.page.query_selector_all(".product-card")
        return [
            {
                "id": c.get_attribute("data-product-id"),
                "price": c.get_attribute("data-price"),
                "color": c.get_attribute("data-color"),
                "name": c.query_selector("h3").inner_text(),
            }
            for c in cards
        ]

    def open_product(self, product_id):
        self.page.goto(f"{self.base_url}/product/{product_id}")

    def add_to_cart(self):
        self.page.click('[data-action="add-to-cart"]')

    def go_to_checkout(self):
        self.page.goto(f"{self.base_url}/checkout")

    def type_card_details(self, card_number, expiry, cvv):
        # visible, char-by-char typing — the "wow" moment on screen
        self.page.type('input[name="card_number"]', card_number, delay=60)
        self.page.type('input[name="card_expiry"]', expiry, delay=60)
        self.page.type('input[name="card_cvv"]', cvv, delay=60)

    def submit_payment(self):
        self.page.click('button[type="submit"]')
```

Razorpay test card to type (official sandbox number, safe to script):
`4111 1111 1111 1111`, any future expiry (e.g. `12/28`), any 3-digit CVV.

---

## 8. Conversation loop (`agent.py`)

Skeleton — the LLM sees tool definitions, decides which to call, you execute
and feed the result back:

```python
TOOLS = [
    {"name": "search_catalog", "description": "Search products by query/color/price"},
    {"name": "select_product", "description": "Pick a specific product by id"},
    {"name": "add_to_cart", "description": "Add current product to cart"},
    {"name": "propose_upsell", "description": "Suggest a related item"},
    {"name": "checkout", "description": "Proceed to payment"},
]

def run_turn(user_message, state):
    response = llm.messages.create(
        model="claude-sonnet-4-6",
        tools=TOOLS,
        messages=state["history"] + [{"role": "user", "content": user_message}],
    )
    for block in response.content:
        if block.type == "tool_use":
            result = dispatch_tool(block.name, block.input, state)
            # gate check happens INSIDE dispatch_tool for any money-moving action
    return response
```

Route every money-moving tool call (`add_to_cart`, `checkout`,
`propose_upsell`) through `gating.py` before it touches the browser.

---

## 9. Gating layer (`gating.py`)

Keep this the way CartMind already has it — deterministic, not LLM-decided:

```python
from dataclasses import dataclass

@dataclass
class Mandate:
    max_order_value: int = 5000
    blocked_categories: tuple = ("accessories",)
    requires_confirmation: bool = True

def check_action(action, cart_total, category, confirmed, mandate: Mandate):
    if category in mandate.blocked_categories:
        return False, f"Category '{category}' is blocked by mandate."
    if cart_total > mandate.max_order_value:
        return False, f"₹{cart_total} exceeds mandate cap of ₹{mandate.max_order_value}."
    if action == "checkout" and not confirmed:
        return False, "No explicit user confirmation on file."
    return True, "OK"
```

Log every call — pass and fail — to `database.py` with a timestamp. This
table **is** your audit trail and your "one failure handled gracefully" demo
moment.

---

## 10. Razorpay integration (`razorpay_service.py`)

```python
import razorpay, os

client = razorpay.Client(auth=(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"]))

def create_order(amount_rupees):
    return client.order.create({
        "amount": amount_rupees * 100,  # paise
        "currency": "INR",
        "payment_capture": 1,
    })

def verify_payment(order_id, payment_id, signature):
    return client.utility.verify_payment_signature({
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature,
    })
```

`storefront/templates/checkout.html` embeds the standard Razorpay Checkout
form (test key) — this is the real form your Playwright script types into.
Use `rzp_test_...` keys only; never live keys in a demo.

---

## 11. Build order (2-day plan)

**Day 1**
1. Storefront: `catalog.json` + search/product/cart pages (2–3 hrs)
2. Razorpay test checkout wired up manually first — click through it
   yourself before automating anything (1 hr)
3. `browser_agent.py` — hardcode a script that searches, filters, adds to
   cart, types a test card, without any LLM yet. Get this rock solid; it's
   your visual centerpiece (2–3 hrs)

**Day 2**
4. `gating.py` + `database.py` audit trail (1–2 hrs)
5. Wire `agent.py` conversation loop on top of the working browser script —
   LLM decides *when* to call each already-working browser action (2–3 hrs)
6. Build and rehearse the one failure case (30 min)
7. Rehearse the full demo end-to-end at least 3 times before presenting —
   this is a live browser automation demo, so timing/selector flakiness is
   your biggest risk, not the AI logic

---

## 12. .env.example

```
ANTHROPIC_API_KEY=sk-ant-...
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
```

Never commit real keys. Use test mode only for the entire project.