# CartMind — Demo Video Script

You're narrating live over a slide deck for the intro, then cutting to your
own screen-recorded demo (already made). Two parts:

## Part 1 — Live-narrated intro (your voice + slides, ~1:15)

Slide deck: **[CartMind Pitch Deck](https://claude.ai/code/artifact/d802104a-054c-403a-bfb4-d4be570725dd)**
— 6 slides (Hook → Problem → Impact → Architecture → Security → Transition),
advance with → or a click while you talk. Read each slide's script beat,
then move on; don't read the slide verbatim, it's there to be glanced at,
not read aloud.

**Slide 1 — Hook** *(~15s)*
> "Would you let an AI spend your money unsupervised? Most people's honest answer is no — not because agents can't shop, but because nothing stops them from getting it wrong, and no one can prove what happened afterward. That gap is what CartMind is about."

**Slide 2 — Problem** *(~15s)*
> "Most 'AI checkout' demos skip the hard part. There's no real spend cap, the only proof a payment happened is the model's own word for it, and if something goes wrong, there's no way to reconstruct why."

**Slide 3 — Impact** *(~20s)*
> "CartMind is a concrete answer, not an argument. Every payment goes through seven independent, deterministic checks — each with a plain-English reason. Two separate gates mean a bug in one can't disable the other. And every attempt, blocked or captured, is reconstructable afterward from a real audit trail."

**Slide 4 — Architecture** *(~15s)*
> "Under the hood it's three planes: the storefront a human and the AI agent both use — same routes, same rules; a policy core neither can bypass; and Razorpay's real checkout, treated as untrusted until verified."

**Slide 5 — Security** *(~15s)*
> "A few things are structurally true here, not just documented: card fields are never reachable from the agent's own code — the only way in is a real browser typing into Razorpay's iframe. The model's claims are never trusted for anything money-related. And this only ever runs in Razorpay TEST MODE — there's no code path that can move real money."

**Slide 6 — Transition** *(~5s)*
> "But this isn't just a design document. Here's what we built."
→ cut directly to your demo recording.

---

## Part 2 — Product demo (your recording)

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

## Reference: original screenshot-driven shot list

You already recorded your own demo — kept here only as a reference for what
each screen/beat was meant to cover, in case you want to reshoot or extend it.

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
