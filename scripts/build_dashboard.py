"""Dựng dashboard 6 panel từ data/logs.jsonl theo contract config/dashboard.yaml.

Chỉ dùng thư viện chuẩn + PyYAML (đã có trong requirements). Output là một file
HTML tĩnh với SVG inline, tự reload theo `refresh_seconds`.

    python scripts/build_dashboard.py            # build một lần
    python scripts/build_dashboard.py --watch    # build lại mỗi refresh_seconds
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

CONFIG = REPO_ROOT / "config" / "dashboard.yaml"
DEFAULT_LOGS = REPO_ROOT / "data" / "logs.jsonl"
DEFAULT_OUT = REPO_ROOT / "data" / "dashboard.html"

# Categorical slots theo thứ tự cố định (light, dark).
SERIES = [("#2a78d6", "#3987e5"), ("#eb6834", "#d95926"), ("#1baf7a", "#199e70"), ("#eda100", "#c98500")]


def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            rec["_ts"] = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
            records.append(rec)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return records


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "usd":
        return f"${value:.4f}"
    if unit == "percent":
        return f"{value:.1f}%"
    if unit == "score_0_to_1":
        return f"{value:.2f}"
    if unit == "ms":
        return f"{value:,.0f} ms"
    if unit == "requests_per_minute":
        return f"{value:,.1f}"
    return f"{value:,.0f}"


def compute(records: list[dict], window_minutes: int, since: datetime | None = None,
            until: datetime | None = None) -> dict:
    if since is not None:
        records = [r for r in records if r["_ts"] >= since]
    if until is not None:
        records = [r for r in records if r["_ts"] <= until]
    if not records:
        return {"minutes": [], "panels": {}, "start": None, "end": None}
    end = max(r["_ts"] for r in records)
    start = since if since is not None else end - timedelta(minutes=window_minutes)
    recs = [r for r in records if r["_ts"] >= start]
    first_minute = min(r["_ts"] for r in recs).replace(second=0, microsecond=0)
    last_minute = end.replace(second=0, microsecond=0)
    minutes = []
    m = first_minute
    while m <= last_minute:
        minutes.append(m)
        m += timedelta(minutes=1)

    by_min: dict[datetime, list[dict]] = defaultdict(list)
    for r in recs:
        by_min[r["_ts"].replace(second=0, microsecond=0)].append(r)

    def per_minute(fn):
        return [fn(by_min.get(mm, [])) for mm in minutes]

    ok = [r for r in recs if r.get("event") == "response_sent"]
    received = [r for r in recs if r.get("event") == "request_received"]
    failed = [r for r in recs if r.get("event") == "request_failed"]
    tool = [r for r in recs if r.get("tool_success") is not None]

    def sent(rs):
        return [r for r in rs if r.get("event") == "response_sent"]

    def err_rate(rs):
        rec_n = sum(1 for r in rs if r.get("event") == "request_received")
        fail_n = sum(1 for r in rs if r.get("event") == "request_failed")
        return fail_n / rec_n * 100 if rec_n else None

    def tool_rate(rs):
        t = [r for r in rs if r.get("tool_success") is not None]
        return sum(1 for r in t if r["tool_success"] is True) / len(t) * 100 if t else None

    lat = [r["latency_ms"] for r in ok]
    error_types: dict[str, int] = defaultdict(int)
    for r in failed:
        error_types[r.get("error_type") or "unknown"] += 1
    span_min = max(1.0, (end - min(r["_ts"] for r in recs)).total_seconds() / 60)

    panels = {
        "latency": {
            "series": {
                "P50": per_minute(lambda rs: percentile([r["latency_ms"] for r in sent(rs)], 50)),
                "P95": per_minute(lambda rs: percentile([r["latency_ms"] for r in sent(rs)], 95)),
                "P99": per_minute(lambda rs: percentile([r["latency_ms"] for r in sent(rs)], 99)),
                "TTFT P95": per_minute(lambda rs: percentile([r["ttft_ms"] for r in sent(rs)], 95)),
            },
            "stats": {
                "p50": percentile(lat, 50), "p95": percentile(lat, 95), "p99": percentile(lat, 99),
                "ttft_p95": percentile([r["ttft_ms"] for r in ok], 95),
            },
        },
        "traffic": {
            "series": {"requests/min": per_minute(lambda rs: sum(1 for r in rs if r.get("event") == "request_received"))},
            "stats": {"count": len(received), "rate_per_minute": len(received) / span_min},
        },
        "errors": {
            "series": {
                "error rate %": per_minute(err_rate),
                "retrieval success %": per_minute(tool_rate),
            },
            "stats": {
                "error_rate_pct": (len(failed) / len(received) * 100) if received else None,
                "tool_success_rate_pct": tool_rate(tool),
                "count_by_value": dict(error_types),
            },
        },
        "cost": {
            "series": {"USD/min": per_minute(lambda rs: sum(r.get("cost_usd", 0) for r in sent(rs)))},
            "stats": {"total": sum(r.get("cost_usd", 0) for r in ok)},
        },
        "tokens": {
            "series": {
                "tokens_in": per_minute(lambda rs: sum(r.get("tokens_in", 0) for r in sent(rs))),
                "tokens_out": per_minute(lambda rs: sum(r.get("tokens_out", 0) for r in sent(rs))),
            },
            "stats": {
                "tokens_in": sum(r.get("tokens_in", 0) for r in ok),
                "tokens_out": sum(r.get("tokens_out", 0) for r in ok),
                "sum_by_field": sum(r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in ok),
            },
        },
        "quality": {
            "series": {"mean quality": per_minute(lambda rs: (sum(r["quality_score"] for r in sent(rs)) / len(sent(rs))) if sent(rs) else None)},
            "stats": {"mean": (sum(r["quality_score"] for r in ok) / len(ok)) if ok else None},
        },
    }
    return {"minutes": minutes, "panels": panels, "start": start, "end": end, "zoom": since is not None or until is not None}


def check(value: float | None, threshold: dict) -> str:
    if value is None:
        return "no-data"
    op, target = threshold["operator"], threshold["value"]
    good = value <= target if op == "lte" else value >= target
    return "ok" if good else "breach"


def svg_chart(minutes: list[datetime], series: dict[str, list], threshold_value: float | None,
              unit: str, threshold_on_chart: bool) -> str:
    w, h, pl, pr, pt, pb = 560, 200, 56, 12, 12, 26
    values = [v for s in series.values() for v in s if v is not None]
    if threshold_on_chart and threshold_value is not None:
        values.append(threshold_value)
    vmax = max(values) if values else 1
    vmax = vmax * 1.1 if vmax > 0 else 1
    if unit == "percent":
        vmax = max(vmax, 100) if any("success" in k for k in series) else vmax
    n = len(minutes)

    def x(i):
        return pl + (w - pl - pr) * (i / (n - 1) if n > 1 else 0.5)

    def y(v):
        return pt + (h - pt - pb) * (1 - v / vmax)

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" preserveAspectRatio="none" class="chart">']
    for frac in (0, 0.5, 1):
        gv = vmax * frac
        parts.append(f'<line class="grid" x1="{pl}" x2="{w - pr}" y1="{y(gv):.1f}" y2="{y(gv):.1f}"/>')
        parts.append(f'<text class="axis" x="{pl - 6}" y="{y(gv) + 4:.1f}" text-anchor="end">{html.escape(fmt(gv, unit))}</text>')
    if minutes:
        for i in sorted({0, n - 1}):
            parts.append(f'<text class="axis" x="{x(i):.1f}" y="{h - 6}" text-anchor="{"start" if i == 0 else "end"}">{minutes[i].strftime("%H:%M")} UTC</text>')
    if threshold_on_chart and threshold_value is not None:
        ty = y(threshold_value)
        parts.append(f'<line class="threshold" x1="{pl}" x2="{w - pr}" y1="{ty:.1f}" y2="{ty:.1f}"/>')
        parts.append(f'<text class="axis" x="{w - pr}" y="{ty - 4:.1f}" text-anchor="end">threshold {html.escape(fmt(threshold_value, unit))}</text>')
    for idx, (name, vals) in enumerate(series.items()):
        pts = [(x(i), y(v), v, minutes[i]) for i, v in enumerate(vals) if v is not None]
        if not pts:
            continue
        cls = f"s{idx + 1}"
        if len(pts) > 1:
            d = " ".join(f"{'M' if j == 0 else 'L'}{px:.1f},{py:.1f}" for j, (px, py, _, _) in enumerate(pts))
            parts.append(f'<path class="line {cls}" d="{d}"/>')
        for px, py, v, mm in pts:
            tip = f"{name} · {mm.strftime('%H:%M')} UTC · {fmt(v, unit)}"
            parts.append(f'<g class="pt"><circle class="hit" cx="{px:.1f}" cy="{py:.1f}" r="10"/>'
                         f'<circle class="dot {cls}" cx="{px:.1f}" cy="{py:.1f}" r="4"/>'
                         f'<title>{html.escape(tip)}</title></g>')
    parts.append("</svg>")
    return "".join(parts)


def render(cfg: dict, data: dict, source: Path) -> str:
    dash = cfg["dashboard"]
    cards = []
    for panel in dash["panels"]:
        pid, unit, th = panel["id"], panel["unit"], panel["threshold"]
        pdata = data["panels"].get(pid, {"series": {}, "stats": {}})
        stats = pdata["stats"]
        headline = stats.get(th["aggregation"])
        state = check(headline if isinstance(headline, (int, float)) else None, th)
        op = "≤" if th["operator"] == "lte" else "≥"
        # Threshold chỉ vẽ lên chart khi cùng thang đo với series theo phút.
        on_chart = th["aggregation"] in {"p95", "error_rate_pct", "mean", "rate_per_minute"}
        chart_unit = "ms" if unit == "ms" else ("percent" if unit == "percent" else unit)
        chart = svg_chart(data["minutes"], pdata["series"], th["value"], chart_unit, on_chart) if data["minutes"] else "<p class='empty'>Chưa có dữ liệu</p>"
        legend = "".join(
            f'<span class="key"><i class="sw s{i + 1}"></i>{html.escape(name)}</span>'
            for i, name in enumerate(pdata["series"])
        ) if len(pdata["series"]) > 1 else ""
        stat_rows = "".join(
            f"<tr><th>{html.escape(k)}</th><td>{html.escape(json.dumps(v) if isinstance(v, dict) else fmt(v, 'usd' if pid == 'cost' else ('percent' if k.endswith('pct') else ('ms' if unit == 'ms' else ('score_0_to_1' if pid == 'quality' else 'n')))))}</td></tr>"
            for k, v in stats.items()
        )
        label = {"ok": "✓ Trong ngưỡng", "breach": "▲ Vượt ngưỡng", "no-data": "— Không có dữ liệu"}[state]
        cards.append(f"""
<section class="card">
  <header><h2>{html.escape(panel['title'])}</h2><span class="unit">{html.escape(unit)}</span></header>
  <div class="headline"><span class="big">{html.escape(fmt(headline if isinstance(headline, (int, float)) else None, 'usd' if pid == 'cost' else unit))}</span>
    <span class="badge {state}">{label}</span>
    <span class="rule">{html.escape(th['aggregation'])} {op} {html.escape(fmt(th['value'], 'usd' if pid == 'cost' else unit))}</span></div>
  {f'<div class="legend">{legend}</div>' if legend else ''}
  {chart}
  <details><summary>Bảng số liệu</summary><table>{stat_rows}</table></details>
</section>""")

    rng = (f"{data['start'].strftime('%Y-%m-%d %H:%M')} → {data['end'].strftime('%H:%M')} UTC"
           if data["start"] else "—")
    css_series_light = "".join(f".s{i + 1}{{--c:{lc}}}" for i, (lc, _) in enumerate(SERIES))
    css_series_dark = "".join(f".s{i + 1}{{--c:{dc}}}" for i, (_, dc) in enumerate(SERIES))
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{dash['refresh_seconds']}">
<title>{html.escape(dash['title'])}</title>
<style>
:root{{--bg:#f4f4f2;--surface:#fcfcfb;--text:#0b0b0b;--text2:#52514e;--muted:#8a8984;--grid:#e6e5e0;--ok:#008300;--bad:#c62828;--border:#e0dfda}}
@media (prefers-color-scheme: dark){{:root{{--bg:#111110;--surface:#1a1a19;--text:#fff;--text2:#c3c2b7;--muted:#8f8e86;--grid:#2c2c2a;--ok:#4caf50;--bad:#ef6b6b;--border:#2c2c2a}}}}
{css_series_light}
@media (prefers-color-scheme: dark){{{css_series_dark}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.top{{padding:20px 16px 8px;max-width:1240px;margin:0 auto}} h1{{margin:0 0 4px;font-size:20px}}
.meta{{color:var(--text2);font-size:13px}} .meta b{{color:var(--text)}}
.grid-wrap{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:16px;padding:12px 16px 32px;max-width:1240px;margin:0 auto}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 14px 10px;min-width:0}}
.card header{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}} h2{{margin:0;font-size:15px}}
.unit{{color:var(--muted);font-size:12px}} .headline{{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;margin:6px 0}}
.big{{font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}} .rule{{color:var(--text2);font-size:12px}}
.badge{{font-size:12px;font-weight:600}} .badge.ok{{color:var(--ok)}} .badge.breach{{color:var(--bad)}} .badge.no-data{{color:var(--muted)}}
.legend{{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--text2);margin-bottom:4px}}
.key{{display:inline-flex;align-items:center;gap:6px}} .sw{{width:10px;height:10px;border-radius:2px;background:var(--c);display:inline-block}}
.chart{{width:100%;height:200px;display:block}} .grid{{stroke:var(--grid);stroke-width:1}}
.axis{{fill:var(--muted);font-size:11px}} .threshold{{stroke:var(--bad);stroke-width:1.5;stroke-dasharray:5 4}}
.line{{fill:none;stroke:var(--c);stroke-width:2;stroke-linejoin:round}} .dot{{fill:var(--c);stroke:var(--surface);stroke-width:2}}
.hit{{fill:transparent}} .pt:hover .dot{{r:6}}
details{{margin-top:6px;font-size:12px;color:var(--text2)}} table{{border-collapse:collapse;margin-top:4px}}
th,td{{text-align:left;padding:2px 12px 2px 0;font-variant-numeric:tabular-nums}} th{{font-weight:500;color:var(--muted)}}
.empty{{color:var(--muted)}}
</style></head><body>
<div class="top"><h1>{html.escape(dash['title'])}</h1>
<div class="meta">Nguồn: <b>{html.escape(source.name)}</b> · Time range: <b>{'zoom sự cố' if data.get('zoom') else str(dash['time_range_minutes']) + ' phút'}</b> ({html.escape(rng)}) · Refresh: <b>{dash['refresh_seconds']}s</b> · Build lúc {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</div></div>
<main class="grid-wrap">{''.join(cards)}</main>
</body></html>"""


def build(logs: Path, out: Path, since: datetime | None = None, until: datetime | None = None) -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    data = compute(load_records(logs) if logs.exists() else [], cfg["dashboard"]["time_range_minutes"], since, until)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(cfg, data, logs), encoding="utf-8")
    print(f"Đã ghi dashboard: {out}")


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, default=DEFAULT_LOGS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--watch", action="store_true", help="Build lại theo refresh_seconds")
    parser.add_argument(
        "--since",
        type=lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
        help="Zoom vào khung sự cố: chỉ dùng log từ thời điểm này (ISO, UTC), ví dụ 2026-09-29T09:03:00Z",
    )
    parser.add_argument(
        "--until",
        type=lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
        help="Chỉ dùng log tới thời điểm này (ISO, UTC)",
    )
    args = parser.parse_args()
    build(args.logs, args.out, args.since, args.until)
    if args.watch:
        refresh = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["dashboard"]["refresh_seconds"]
        while True:
            time.sleep(refresh)
            build(args.logs, args.out, args.since, args.until)


if __name__ == "__main__":
    main()
