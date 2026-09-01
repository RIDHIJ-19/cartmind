# CartMind — Demo Video Script (~3:30)

Two parts: a cinematic AI-generated vision intro (~1:30), then the real
product demo (~2:00, screenshot-driven — see below).

## Part 1 — Cinematic vision intro (0:00–1:30)

Seven short AI-generated clips (8–12s each), abstract visuals only — no
literal UI or readable text inside the generated footage itself (video
generators distort both); all real text/branding/voiceover added afterward
in an editor. Total generated footage ≈83s + title cards ≈1:30.

| # | Time | Clip (generate) | Voiceover / overlay |
|---|---|---|---|
| 1 | 0:00–0:10 | Fragmented online shopping: scrolling, tabs, filters, abandoned carts, a failed payment icon | "Online commerce is faster than ever. But finding what you want is still complicated — and every transaction tells a story nobody's reading." |
| 2 | 0:10–0:22 | Voice waves forming near a dark futuristic interface; the waves resolve into soft shapes | "What if commerce could simply understand you?" |
| 3 | 0:22–0:34 | Voice waves morphing into abstract product tiles that self-organize by color/price into flowing groups | "Discover. Explore. Buy — by having a conversation." |
| 4 | 0:34–0:44 | A single glowing transaction point expanding outward into a network of flowing data streams | "But the journey doesn't end when a customer clicks pay." |
| 5 | 0:44–0:59 | Data streams converging into a rising dashboard: bar charts, revenue lines, connected nodes | "Behind every purchase is an insight waiting to be found." |
| 6 | 0:59–1:11 | An abstract warehouse/grid of glowing nodes — some dim (low stock), one pulsing forward (forecast) | "From payments to inventory — moving beyond watching data, to acting on it." |
| 7 | 1:11–1:23 | All prior visuals converge into one connected ring: customer → agent → payment → data → growth | "A smarter journey for the customer. A clearer picture for the business. One connected layer for commerce." |

**[1:23–1:30] Transition into the demo**
Visual: the cinematic world dissolves into the real CartMind storefront (`search.png`).
> "But this isn't just an idea. This is what we built." → **Beyond the Vision. Here is the Experience.**

---

## Part 2 — Product demo (1:30–3:30)

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

## Script (screenshot-driven)

Each scene: screenshot(s) to show, and a short overlay line (kept under ~120 characters each so it fits as a single video-tool prompt/caption, not a paragraph).

**[1:30–1:42] Opening** — `search.png` → `chatbot.png`
> Beyond payments. Towards smarter commerce.

**[1:42–2:00] Conversational discovery** — `chatbot.png` (zoom chat) → live: "I want a dress" → results
> Type or speak. Find what you want — without searching endlessly.

**[2:00–2:20] Shopping journey** — `product.png` → `cart.png` → live: add a second item
> A shopping companion, not a one-shot lookup.

**[2:20–2:40] Checkout + live payment** — `checkout.png` → `live_view.png` → `order_confirmed.png` (+ brief `order_failed.png`)
> Every transaction. Every outcome. Fully visible. (TEST MODE only — no real charge)

**[2:40–2:45] Transition** — cut to black
> But what happens after the customer clicks Pay?

**[2:45–3:10] Owner dashboard** — `owner.png` pan: stat cards → funnel → manual-vs-agent → blocked ledger
> Don't just see failures. Understand them.

**[3:10–3:30] Inventory intelligence + close** — `owner.png` (forecast panel)
> From conversation to conversion. From payment to insight.

## Alternate taglines
- "Beyond Payments. Smarter Commerce."
- "Every Purchase Tells a Story. Understand the Whole Story."
- "Discover. Pay. Analyze. Grow."
