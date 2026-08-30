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

## Script

**[0:00–0:30] Problem**
AI agents doing shopping/payments on your behalf sounds great — but how do you trust an AI with your money? No caps, no audit trail, no way to prove what it did.

**[0:30–1:00] Solution + core pitch**
CartMind: an AI shopping agent with a gated, auditable payment flow. Every payment goes through a 7-check safety gate + spend cap + explicit confirmation — before Razorpay ever sees it. Nothing moves without proof.

**[1:00–1:30] Feature tour (fast cuts)**
- Chat: search → add to cart → checkout → pay, by voice or text
- Live view: watch the agent type the real card into Razorpay live
- Owner dashboard: see exactly what the agent did and why, in numbers

**[1:30–2:00] How it works (backend, 30s)**
Flask storefront + LLM tool-calling. The model can only *request* actions — the server decides what's allowed. A Playwright browser drives the real Razorpay iframe (card fields are sandboxed by design, so this is the only way in). Every check, pass or fail, is logged to Postgres.

**[2:00–2:30] One issue + fix**
Two real bumps: (1) LLM cost/reliability — switched to a smaller model + tightened prompts + forced tool-calls so it can't fake success. (2) Payment wasn't visible on a hosted server — built a live CDP screencast over WebSocket so you can watch the card get typed in real time, even headless.

**[2:30+] Live demo**
Add to cart → checkout → pay by voice → show live stream → show order confirmed → show owner dashboard updating.
