"""Aggregation and chart-geometry for the owner console (storefront/app.py's
/owner route). Pulled out of app.py because the route had grown to ~285
lines mixing authentication, data aggregation, and four different SVG
chart-geometry calculations (donut segments, funnel polygon, gauge needle,
sparkline path) inline — this module holds the geometry/aggregation, the
route just does auth and hands data through to the template."""

import math
from datetime import datetime, timedelta, timezone

SUCCESS_STATUSES = ("paid", "captured", "success")
SIGNAL_RANK = {"reorder": 0, "watch": 1, "slow": 2, "steady": 3}
SIGNAL_ICONS = {"reorder": "&#9888;", "watch": "&#128064;", "slow": "&#128200;", "steady": "&#10003;"}
STATUS_COLORS = {
    "paid": "#067d62", "captured": "#067d62", "success": "#067d62",
    "failed": "#b12704", "created": "#c45500", "awaiting_checkout": "#c45500",
}
CATEGORY_PALETTE = ["#ff8a3d", "#131921", "#3d7bff", "#0aab7c", "#c45500", "#9061e8"]
FUNNEL_COLORS = ["#131921", "#3d4a63", "#ff8a3d", "#0aab7c"]
CHANNEL_COLORS = {"manual": "#131921", "agent": "#ff8a3d"}
CHANNEL_LABELS = {"manual": "Manual checkout", "agent": "Chat agent"}


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


def _donut_segments(counts, palette_or_map, total=None):
    """Shared donut-chart math for status/category/channel breakdowns."""
    radius, circumference = 52, 2 * math.pi * 52
    total = total if total is not None else (sum(counts.values()) or 1)
    segments = []
    offset = 0.0
    color_fn = palette_or_map if callable(palette_or_map) else (lambda key, i: palette_or_map.get(key, "#565959"))
    for i, (key, n) in enumerate(sorted(counts.items(), key=lambda kv: -kv[1])):
        pct = n / total
        length = pct * circumference
        segments.append({
            "key": key, "n": n, "pct": round(pct * 100, 1),
            "color": color_fn(key, i),
            "dasharray": f"{length:.2f} {circumference - length:.2f}",
            "offset": round(-offset, 2),
        })
        offset += length
    return segments, circumference, total


def build_dashboard_context(database, catalog, catalog_by_sku, policy_cap):
    """Compute everything the owner.html template needs. Returns a dict
    meant to be passed straight through as render_template kwargs."""
    snap = database.snapshot()
    payments = snap["payments"]
    events = snap["events"]
    stats = database.payment_stats()
    all_sku_sales = database.sku_sales()
    sold_by_sku = {row["sku"]: row["quantity"] for row in all_sku_sales}
    sku_sales = all_sku_sales[:8]
    blocked = database.blocked_events(10)

    demand = []
    for p in catalog:
        sold = sold_by_sku.get(p["sku"], 0)
        info = _demand_signal(p.get("stock", 0), sold)
        demand.append({"sku": p["sku"], "name": p["name"], "stock": p.get("stock", 0), "sold": sold, **info})
    demand.sort(key=lambda row: (SIGNAL_RANK.get(row["signal"], 9), -row["sold"]))
    low_stock = [row for row in demand if row["signal"] == "reorder"]

    max_stock = max((row["stock"] for row in demand), default=1) or 1
    for row in demand:
        row["stock_pct"] = round(row["stock"] / max_stock * 100)
        row["icon"] = SIGNAL_ICONS.get(row["signal"], "")
    demand_summary = {key: sum(1 for row in demand if row["signal"] == key) for key in SIGNAL_RANK}

    volume = sum(p["amount_inr"] for p in payments if p["status"] in SUCCESS_STATUSES)

    today = datetime.now(timezone.utc).date()
    days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    by_day = {d.isoformat(): 0 for d in days}
    for p in payments:
        if p["status"] not in SUCCESS_STATUSES:
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

    donut_raw, circumference, total_payments = _donut_segments(status_counts, STATUS_COLORS)
    donut_segments = [{**seg, "status": seg["key"]} for seg in donut_raw]

    category_revenue = {}
    for row in all_sku_sales:
        cat = catalog_by_sku.get(row["sku"], {}).get("category", "other")
        category_revenue[cat] = category_revenue.get(cat, 0) + row["revenue_inr"]
    revenue_by_sku = {row["sku"]: row["revenue_inr"] for row in all_sku_sales}
    category_raw, _, _ = _donut_segments(
        category_revenue,
        lambda key, i: CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)],
    )
    category_segments = [{**seg, "category": seg["key"], "revenue": seg["n"]} for seg in category_raw]

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
    channel_total = sum(c["total"] for c in channel_raw.values()) or 1
    channel_donut, _, _ = _donut_segments(
        {key: channel_raw[key]["total"] for key in ("manual", "agent")},
        CHANNEL_COLORS,
        total=channel_total,
    )
    channel_segments = [
        {**seg, "label": CHANNEL_LABELS[seg["key"]], "captured": channel_raw[seg["key"]]["captured"]}
        for seg in channel_donut
    ]

    watch_items = [row for row in demand if row["signal"] == "watch"]
    slow_items = [row for row in demand if row["signal"] == "slow"]
    recent_blocks = database.recent_blocked_count(60)
    recent_failed = database.recent_event_count(minutes=60, action="payment_failed")

    alerts = _build_alerts(low_stock, recent_blocks, recent_failed, watch_items, slow_items, stats, database)

    ledger = [
        {
            "payment": p,
            "trail": _match_events(events, p),
            "item_summary": _item_summary(p),
            "created_display": _display_time(p.get("created_at")),
        }
        for p in payments
    ]

    return dict(
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


def _build_alerts(low_stock, recent_blocks, recent_failed, watch_items, slow_items, stats, database):
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
    # All-time failure rate — complements the last-hour spike alert above with
    # a lifetime view, so a slow-burn problem (not just a sudden spike) still
    # surfaces.
    if stats["failed"] >= 3:
        fail_pct = round((stats["failed"] / stats["initiated"]) * 100, 1) if stats["initiated"] else 0
        alerts.append({
            "severity": "warning", "icon": "&#10060;",
            "title": f"{stats['failed']} failed payments all-time ({fail_pct}% of all attempts)",
            "detail": "Lifetime total, not just the last hour — a steady failure rate is as worth investigating as a spike.",
        })
    # Which gate is actually doing the rejecting, over the same broader
    # window used for the ledger below — tallied from the seven-check
    # decision's ruleViolated field (falls back to the action name for the
    # cart-policy gate, which doesn't break down into named sub-checks).
    rule_counts = {}
    for ev in database.blocked_events(200):
        rule = (ev.get("details") or {}).get("ruleViolated") or ev.get("action", "unknown")
        rule_counts[rule] = rule_counts.get(rule, 0) + 1
    if rule_counts:
        top_rule, top_count = max(rule_counts.items(), key=lambda kv: kv[1])
        if top_count >= 3:
            alerts.append({
                "severity": "info", "icon": "&#128272;",
                "title": f"{top_rule.replace('_', ' ').title()} is the most common block reason ({top_count})",
                "detail": "Worth checking whether this limit is set correctly for real traffic, or whether it's catching what it should.",
            })
    return alerts
