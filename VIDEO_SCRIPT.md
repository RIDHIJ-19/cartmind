# CartMind — Demo Video Script (~2:30)

## Feature/page inventory (for brainstorming)

- **Search / catalog** — browse all products, filter by department/color/price
- **Product page** — single item detail view
- **Cart** — review items before checkout
- **Checkout** — real Razorpay TEST MODE order, "Pay with Razorpay" button
- **Order confirmed** — success page with item summary, order ID, amount
- **Order failed** — honest failure page, no charge made
- **Chat widget** — talk/type to search, add to cart, checkout, pay — no login needed
- **Voice input** — mic button, speech-to-text via Groq Whisper
- **Live payment stream** — watch the AI type the card into Razorpay in real time (via WebSocket)
- **Owner console** — revenue, funnel, manual-vs-agent split, blocked-attempt ledger, full payment history

## Owner console — panel by panel

- **Top stat cards** (captured volume, success rate, successful orders, avg. order value) — the headline health of the store, at a glance.
- **Low-stock banner** — flags items selling faster than remaining stock covers, before they run out.
- **Revenue analytics (7-day)** — trend line of captured revenue only; blocked/failed attempts never inflate it.
- **Revenue by category** — which product category actually drives money, not just traffic.
- **Manual vs. chat-agent checkouts** — proves the AI is held to the same bar as a human, side by side.
- **Capture rate by channel** — same comparison as a %, so a dip in agent reliability is visible immediately.
- **Checkout funnel** (attempts → cart policy → safety kernel → captured) — shows exactly *which* gate is rejecting traffic, not just a pass/fail total.
- **Policy cap usage gauge** — how close average orders run to the hard spend cap; headroom, not a bottleneck.
- **Payment ledger** — every order, expandable, with the exact gate steps and plain-English reason for its verdict.
- **Top SKUs by revenue** — what's actually selling, ranked by money not units.
- **Blocked attempts** — the "nothing handled gracefully" list — every rejected checkout, with the exact rule that stopped it.
- **Inventory & demand forecast** — rule-based reorder/promote/no-action signal per product, with the plain-English "why."

### Alert types (top banner)

- **Critical — low stock** — item(s) out of stock or selling faster than remaining cover.
- **Warning — blocked spike (last hour)** — a sudden burst of rejected checkouts just now.
- **Warning — failed spike (last hour)** — cards declining/checkout abandoned more than usual, right now.
- **Warning — failed all-time** — a *steady* failure rate over the store's whole history, not just a spike — catches slow-burn problems the hourly alert would miss.
- **Info — top block reason** — which single gate (e.g. transaction limit) is rejecting the most attempts overall, so you know what to tune.
- **Info — watch list** — products running low, not urgent yet.
- **Info — slow movers** — products with zero captured sales, candidates for a promotion.

### Payment ledger — every status a row can show

- **Created** — order made with Razorpay, payment not yet attempted or still in progress.
- **Captured** — paid and cryptographically verified; this is the only state that counts as revenue anywhere on the dashboard.
- **Failed** — card declined, checkout abandoned, or verification failed — no charge occurred.

### Blocked-attempt types (the two gates, by name)

- **Cart-policy block** — over the hard order-value cap, or a blocked category — stopped before the safety kernel even runs.
- **Safety-kernel block** — one of the seven checks failed: authorization mismatch, amount mismatch, transaction limit, quantity limit, discount limit, rate limit, or duplicate payment — each with its own plain-English reason.

## Script (2:00, screenshot-driven)

Each scene names the exact screenshot(s) to show from `docs/screenshots/`, live footage to capture instead, and the voiceover/overlay line. Keep cuts fast — no screen holds longer than the line takes to say.

**[0:00–0:12] Opening**
Screens: `search.png`, then `chatbot.png`.
> "What if payments could do more than process a transaction — what if the same platform could help customers find what they want, and help the business understand everything happening behind every purchase? This is CartMind: an AI shopping agent with a gated, auditable payment flow."

**[0:12–0:30] Conversational discovery**
Screens: `chatbot.png` (zoom on the chat panel), then live footage of typing "I want a dress" → results appearing.
> "Shopping starts with a conversation, typed or spoken. Ask for a product, a color, a price range — CartMind narrows the catalog instead of making you scroll it."

**[0:30–0:50] Shopping journey**
Screens: `product.png` → `cart.png` → live footage adding a second item (e.g. "add a shirt too").
> "Explore a product, add it to cart, then keep going — ask for something else and it searches, shows results, and adds again. It's a shopping companion, not a one-shot lookup."

**[0:50–1:10] Checkout and live payment**
Screens: `checkout.png` → `live_view.png` → `order_confirmed.png` (and briefly `order_failed.png`).
> "Checkout runs through a real payment flow on Razorpay TEST MODE — a safe, controlled replica, not a live commercial site, so the entire journey can be demonstrated without real credentials or production bot defenses. Every card gets typed into the real checkout iframe live, streamed so you can watch it happen — and every outcome, success or failure, is fully visible, never hidden."

**[1:10–1:15] Transition**
> "But what happens after the customer clicks Pay?"

**[1:15–1:40] Owner dashboard — business intelligence**
Screens: `owner.png` (pan across stat cards → funnel → manual-vs-agent split → blocked-attempt ledger).
> "The owner dashboard turns every transaction into insight: revenue, success rate, and average order value at a glance; a checkout funnel showing exactly where customers drop off; manual shopping compared side-by-side with the AI agent; and when a payment fails, the exact stage and reason — not just a red X."

**[1:40–2:00] Inventory intelligence + close**
Screens: `owner.png` (low-stock/forecast panel).
> "It looks past payments too — flagging products selling faster than stock covers, and slow movers worth promoting. From conversation to conversion, from payment to insight: CartMind is the intelligence layer around commerce, not just the payment gateway."

## Alternate taglines
- "Beyond Payments. Smarter Commerce."
- "Every Purchase Tells a Story. Understand the Whole Story."
- "Discover. Pay. Analyze. Grow."
