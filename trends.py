"""Google Trends Research Script — find rising niches and product opportunities.

Usage:
    python trends.py                          # Interactive mode
    python trends.py "standing desk"          # Quick research on a term
    python trends.py "standing desk" "treadmill desk" --shopping
    python trends.py --trending               # Today's trending searches
    python trends.py --discover "home office" # Deep niche discovery
    python trends.py --compare "product A" "product B" "product C"

Output:
    Prints to terminal with color. Saves detailed results to trends_results/
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Fix pytrends + urllib3 2.x compatibility (method_whitelist → allowed_methods)
import urllib3
if not hasattr(urllib3.util.retry.Retry.__init__, '_patched'):
    _orig_init = urllib3.util.retry.Retry.__init__
    def _patched_init(self, *args, **kwargs):
        if 'method_whitelist' in kwargs:
            kwargs['allowed_methods'] = kwargs.pop('method_whitelist')
        return _orig_init(self, *args, **kwargs)
    _patched_init._patched = True
    urllib3.util.retry.Retry.__init__ = _patched_init

from pytrends.request import TrendReq

# ── Config ────────────────────────────────────────────────────────────
RESULTS_DIR = Path(__file__).parent / "trends_results"
REQUEST_DELAY = (4, 10)  # random delay range between API calls (seconds)
MAX_RETRIES = 3
GEO = "US"
TIMEFRAME = "today 12-m"

# ANSI colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_CYAN = "\033[96m"
C_AMBER = "\033[33m"


# ── Helpers ───────────────────────────────────────────────────────────

def _delay():
    """Polite delay between requests to avoid rate limiting."""
    time.sleep(random.uniform(*REQUEST_DELAY))


def _safe_call(func, *args, **kwargs):
    """Call a pytrends method with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            result = func(*args, **kwargs)
            _delay()
            return result
        except Exception as e:
            msg = str(e)
            if "429" in msg or "Too Many" in msg:
                wait = 30 * (attempt + 1)
                print(f"  {C_YELLOW}Rate limited. Waiting {wait}s...{C_RESET}")
                time.sleep(wait)
            elif attempt < MAX_RETRIES - 1:
                print(f"  {C_DIM}Retry {attempt + 1}: {e}{C_RESET}")
                time.sleep(10)
            else:
                print(f"  {C_RED}Failed after {MAX_RETRIES} attempts: {e}{C_RESET}")
                return None
    return None


def _init_pytrends() -> TrendReq:
    return TrendReq(hl="en-US", tz=360, retries=3, backoff_factor=1.0)


def _make_json_safe(obj):
    """Recursively convert pandas/numpy objects so json.dump can handle them."""
    if isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj


def _save_results(name: str, data: dict) -> Path:
    """Save results as JSON to trends_results/."""
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip()
    path = RESULTS_DIR / f"{safe_name}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_make_json_safe(data), f, indent=2, ensure_ascii=False, default=str)
    return path


# ── Commands ──────────────────────────────────────────────────────────

def cmd_trending(geo: str = GEO):
    """Show today's trending searches."""
    print(f"\n{C_BOLD}{C_CYAN}=== Trending Searches ({geo}) ==={C_RESET}\n")
    pt = _init_pytrends()
    trending = _safe_call(pt.trending_searches, pn="united_states" if geo == "US" else geo.lower())
    if trending is None or trending.empty:
        print(f"  {C_RED}No trending data available.{C_RESET}")
        return

    for i, term in enumerate(trending[0].head(20)):
        print(f"  {C_AMBER}{i + 1:>3}.{C_RESET} {term}")

    # Also try realtime trending
    print(f"\n{C_BOLD}{C_CYAN}=== Realtime Trending ==={C_RESET}\n")
    try:
        realtime = _safe_call(pt.realtime_trending_searches, pn=geo)
        if realtime is not None and not realtime.empty:
            titles = realtime["title"].head(15) if "title" in realtime.columns else []
            for i, title in enumerate(titles):
                print(f"  {C_AMBER}{i + 1:>3}.{C_RESET} {title}")
        else:
            print(f"  {C_DIM}No realtime data available.{C_RESET}")
    except Exception:
        print(f"  {C_DIM}Realtime trending not available.{C_RESET}")


def cmd_research(keywords: list[str], geo: str = GEO, timeframe: str = TIMEFRAME,
                 shopping: bool = False):
    """Full research on 1-5 keywords: interest, related queries, regions."""
    gprop = "froogle" if shopping else ""
    search_type = "Google Shopping" if shopping else "Web Search"
    kw_str = ", ".join(keywords)

    print(f"\n{C_BOLD}{C_CYAN}=== Research: {kw_str} ==={C_RESET}")
    print(f"  {C_DIM}Geo: {geo} | Time: {timeframe} | Type: {search_type}{C_RESET}\n")

    pt = _init_pytrends()
    pt.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo, gprop=gprop)

    results = {"keywords": keywords, "geo": geo, "timeframe": timeframe, "type": search_type}

    # ── Interest over time ────────────────────────────────────────
    print(f"{C_BOLD}Interest Over Time{C_RESET}")
    iot = _safe_call(pt.interest_over_time)
    if iot is not None and not iot.empty:
        # Show trend direction
        for kw in keywords:
            if kw in iot.columns:
                values = iot[kw].values
                recent = values[-4:].mean() if len(values) >= 4 else values[-1]
                older = values[:4].mean() if len(values) >= 4 else values[0]
                current = int(values[-1])
                peak = int(values.max())

                if recent > older * 1.2:
                    trend = f"{C_GREEN}RISING{C_RESET}"
                elif recent < older * 0.8:
                    trend = f"{C_RED}DECLINING{C_RESET}"
                else:
                    trend = f"{C_YELLOW}STABLE{C_RESET}"

                print(f"  {kw}: current={current}, peak={peak}, trend={trend}")

        results["interest_over_time"] = {str(k): v for k, v in iot.to_dict().items()}
    else:
        print(f"  {C_DIM}No data available.{C_RESET}")
    print()

    # ── Related queries (THE GOLD) ────────────────────────────────
    print(f"{C_BOLD}Related Queries{C_RESET}")
    related = _safe_call(pt.related_queries)
    results["related_queries"] = {}

    if related:
        for kw in keywords:
            if kw not in related:
                continue
            data = related[kw]
            results["related_queries"][kw] = {"rising": [], "top": []}

            # Rising queries
            rising = data.get("rising")
            if rising is not None and not rising.empty:
                print(f"\n  {C_GREEN}Rising queries for '{kw}':{C_RESET}")
                rising_sorted = rising.sort_values("value", ascending=False)
                for _, row in rising_sorted.head(15).iterrows():
                    val = row["value"]
                    query = row["query"]
                    if val >= 5000:
                        label = f"{C_RED}{C_BOLD}BREAKOUT{C_RESET}"
                    elif val >= 1000:
                        label = f"{C_YELLOW}+{int(val)}%{C_RESET}"
                    else:
                        label = f"{C_GREEN}+{int(val)}%{C_RESET}"
                    print(f"    {label:>25}  {query}")
                    results["related_queries"][kw]["rising"].append({
                        "query": query, "growth": int(val)
                    })

            # Top queries
            top = data.get("top")
            if top is not None and not top.empty:
                print(f"\n  {C_BLUE}Top queries for '{kw}':{C_RESET}")
                top_sorted = top.sort_values("value", ascending=False)
                for _, row in top_sorted.head(10).iterrows():
                    print(f"    {int(row['value']):>8}  {row['query']}")
                    results["related_queries"][kw]["top"].append({
                        "query": row["query"], "score": int(row["value"])
                    })
    else:
        print(f"  {C_DIM}No related queries data.{C_RESET}")
    print()

    # ── Related topics ────────────────────────────────────────────
    print(f"{C_BOLD}Related Topics{C_RESET}")
    results["related_topics"] = {}
    try:
        topics = _safe_call(pt.related_topics)
        if topics:
            for kw in keywords:
                if kw not in topics:
                    continue
                data = topics[kw]

                rising = data.get("rising")
                if rising is not None and not rising.empty:
                    print(f"\n  {C_GREEN}Rising topics for '{kw}':{C_RESET}")
                    for _, row in rising.head(10).iterrows():
                        title = row.get("topic_title", "?")
                        val = row.get("value", 0)
                        topic_type = row.get("topic_type", "")
                        if val >= 5000:
                            label = f"{C_RED}{C_BOLD}BREAKOUT{C_RESET}"
                        else:
                            label = f"{C_GREEN}+{int(val)}%{C_RESET}"
                        print(f"    {label:>25}  {title} {C_DIM}({topic_type}){C_RESET}")
        else:
            print(f"  {C_DIM}No related topics data.{C_RESET}")
    except Exception as e:
        print(f"  {C_DIM}Related topics unavailable ({e}).{C_RESET}")
    print()

    # ── Interest by region ────────────────────────────────────────
    print(f"{C_BOLD}Interest by Region{C_RESET}")
    results["regions"] = {}
    try:
        regions = _safe_call(pt.interest_by_region, resolution="REGION" if geo else "COUNTRY")
        if regions is not None and not regions.empty:
            for kw in keywords:
                if kw in regions.columns:
                    top_regions = regions[kw].sort_values(ascending=False).head(10)
                    print(f"\n  {C_BLUE}Top regions for '{kw}':{C_RESET}")
                    for region, value in top_regions.items():
                        if value > 0:
                            bar = "█" * (value // 5)
                            print(f"    {region:>25}  {C_AMBER}{bar}{C_RESET} {value}")
                    results["regions"][kw] = top_regions.to_dict()
        else:
            print(f"  {C_DIM}No regional data.{C_RESET}")
    except Exception:
        print(f"  {C_DIM}Regional data unavailable.{C_RESET}")
    print()

    # ── Save results ──────────────────────────────────────────────
    path = _save_results(keywords[0], results)
    print(f"{C_DIM}Results saved to: {path}{C_RESET}\n")


def cmd_discover(seed: str, geo: str = GEO, timeframe: str = TIMEFRAME):
    """Deep niche discovery: research a seed term, then drill into its top rising queries."""
    print(f"\n{C_BOLD}{C_CYAN}=== Niche Discovery: '{seed}' ==={C_RESET}")
    print(f"  {C_DIM}Phase 1: Research seed term{C_RESET}")
    print(f"  {C_DIM}Phase 2: Drill into top rising queries{C_RESET}\n")

    pt = _init_pytrends()

    # Phase 1: Get rising queries for the seed
    pt.build_payload([seed], cat=0, timeframe=timeframe, geo=geo, gprop="")
    related = _safe_call(pt.related_queries)

    if not related or seed not in related:
        print(f"  {C_RED}No data for seed term.{C_RESET}")
        return

    rising = related[seed].get("rising")
    if rising is None or rising.empty:
        print(f"  {C_RED}No rising queries found for '{seed}'.{C_RESET}")
        return

    # Collect top rising queries
    rising_sorted = rising.sort_values("value", ascending=False)
    drill_targets = []

    print(f"{C_BOLD}Phase 1 — Rising queries for '{seed}':{C_RESET}\n")
    for _, row in rising_sorted.head(20).iterrows():
        val = row["value"]
        query = row["query"]
        if val >= 5000:
            label = f"{C_RED}{C_BOLD}BREAKOUT{C_RESET}"
        else:
            label = f"{C_GREEN}+{int(val)}%{C_RESET}"
        print(f"  {label:>25}  {query}")
        if len(drill_targets) < 5:
            drill_targets.append(query)

    print(f"\n{C_BOLD}Phase 2 — Drilling into top {len(drill_targets)} rising queries...{C_RESET}\n")

    all_opportunities = []

    for target in drill_targets:
        print(f"  {C_CYAN}Researching: {target}{C_RESET}")
        try:
            pt.build_payload([target], cat=0, timeframe=timeframe, geo=geo, gprop="")

            # Get interest to check trend direction
            iot = _safe_call(pt.interest_over_time)
            trend_dir = "?"
            if iot is not None and not iot.empty and target in iot.columns:
                values = iot[target].values
                recent = values[-4:].mean() if len(values) >= 4 else values[-1]
                older = values[:4].mean() if len(values) >= 4 else values[0]
                if recent > older * 1.2:
                    trend_dir = "RISING"
                elif recent < older * 0.8:
                    trend_dir = "DECLINING"
                else:
                    trend_dir = "STABLE"

            # Get its rising queries (sub-niches)
            sub_related = _safe_call(pt.related_queries)
            sub_rising = []
            if sub_related and target in sub_related:
                sr = sub_related[target].get("rising")
                if sr is not None and not sr.empty:
                    for _, row in sr.head(5).iterrows():
                        sub_rising.append({
                            "query": row["query"],
                            "growth": int(row["value"]),
                        })

            all_opportunities.append({
                "query": target,
                "trend": trend_dir,
                "sub_niches": sub_rising,
            })
        except Exception as e:
            print(f"    {C_DIM}Skipped: {e}{C_RESET}")

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{C_BOLD}{C_CYAN}=== Discovery Summary ==={C_RESET}\n")
    for opp in all_opportunities:
        trend_color = C_GREEN if opp["trend"] == "RISING" else C_YELLOW if opp["trend"] == "STABLE" else C_RED
        print(f"  {trend_color}{opp['trend']:>10}{C_RESET}  {C_BOLD}{opp['query']}{C_RESET}")
        for sub in opp["sub_niches"]:
            g = sub["growth"]
            gl = f"{C_RED}BREAKOUT{C_RESET}" if g >= 5000 else f"{C_GREEN}+{g}%{C_RESET}"
            print(f"             {gl:>25}  {sub['query']}")

    # Save
    results = {
        "seed": seed, "geo": geo, "timeframe": timeframe,
        "opportunities": all_opportunities,
    }
    path = _save_results(f"discover_{seed}", results)
    print(f"\n{C_DIM}Results saved to: {path}{C_RESET}\n")


def cmd_compare(keywords: list[str], geo: str = GEO, timeframe: str = "today 5-y"):
    """Compare up to 5 keywords head-to-head over time."""
    print(f"\n{C_BOLD}{C_CYAN}=== Compare: {', '.join(keywords)} ==={C_RESET}")
    print(f"  {C_DIM}Geo: {geo} | Time: {timeframe}{C_RESET}\n")

    pt = _init_pytrends()
    pt.build_payload(keywords[:5], cat=0, timeframe=timeframe, geo=geo, gprop="")

    iot = _safe_call(pt.interest_over_time)
    if iot is None or iot.empty:
        print(f"  {C_RED}No comparison data.{C_RESET}")
        return

    print(f"{C_BOLD}Current standings:{C_RESET}\n")
    rankings = []
    for kw in keywords:
        if kw not in iot.columns:
            continue
        values = iot[kw].values
        current = int(values[-1])
        peak = int(values.max())
        avg = int(values.mean())
        recent = values[-4:].mean() if len(values) >= 4 else values[-1]
        older = values[:4].mean() if len(values) >= 4 else values[0]

        if recent > older * 1.2:
            trend = f"{C_GREEN}RISING{C_RESET}"
        elif recent < older * 0.8:
            trend = f"{C_RED}DECLINING{C_RESET}"
        else:
            trend = f"{C_YELLOW}STABLE{C_RESET}"

        rankings.append((current, kw, peak, avg, trend))

    rankings.sort(reverse=True)
    for i, (current, kw, peak, avg, trend) in enumerate(rankings):
        bar = "█" * (current // 3)
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "  "
        print(f"  {medal} {kw:>25}  now={current:>3}  peak={peak:>3}  avg={avg:>3}  {trend}  {C_AMBER}{bar}{C_RESET}")

    path = _save_results("compare_" + keywords[0], {
        "keywords": keywords, "geo": geo, "timeframe": timeframe,
        "rankings": [{"keyword": kw, "current": c, "peak": p, "avg": a}
                     for c, kw, p, a, _ in rankings],
    })
    print(f"\n{C_DIM}Results saved to: {path}{C_RESET}\n")


def cmd_interactive():
    """Interactive research mode."""
    print(f"\n{C_BOLD}{C_CYAN}=== Google Trends Research Tool ==={C_RESET}")
    print(f"  {C_DIM}Commands:{C_RESET}")
    print(f"    {C_AMBER}research <term>{C_RESET}    — Full research on a keyword")
    print(f"    {C_AMBER}discover <term>{C_RESET}    — Deep niche discovery")
    print(f"    {C_AMBER}compare <a> <b>{C_RESET}    — Compare keywords head-to-head")
    print(f"    {C_AMBER}trending{C_RESET}           — Today's trending searches")
    print(f"    {C_AMBER}shopping <term>{C_RESET}    — Research with Google Shopping data")
    print(f"    {C_AMBER}quit{C_RESET}               — Exit\n")

    while True:
        try:
            raw = input(f"{C_AMBER}trends>{C_RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            print("Bye.")
            break
        elif cmd == "trending":
            cmd_trending()
        elif cmd == "research":
            if not args:
                print(f"  {C_RED}Usage: research <keyword>{C_RESET}")
                continue
            keywords = [k.strip() for k in args.split(",")]
            cmd_research(keywords)
        elif cmd == "discover":
            if not args:
                print(f"  {C_RED}Usage: discover <seed keyword>{C_RESET}")
                continue
            cmd_discover(args.strip())
        elif cmd == "compare":
            if not args:
                print(f"  {C_RED}Usage: compare <keyword1>, <keyword2>{C_RESET}")
                continue
            keywords = [k.strip() for k in args.split(",")]
            if len(keywords) < 2:
                print(f"  {C_RED}Need at least 2 keywords (comma-separated){C_RESET}")
                continue
            cmd_compare(keywords)
        elif cmd == "shopping":
            if not args:
                print(f"  {C_RED}Usage: shopping <keyword>{C_RESET}")
                continue
            keywords = [k.strip() for k in args.split(",")]
            cmd_research(keywords, shopping=True)
        else:
            # Treat as a research query
            keywords = [k.strip() for k in raw.split(",")]
            cmd_research(keywords)


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Google Trends Research — find rising niches and product opportunities",
    )
    parser.add_argument("keywords", nargs="*", help="Keywords to research (comma or space separated)")
    parser.add_argument("--trending", action="store_true", help="Show today's trending searches")
    parser.add_argument("--discover", metavar="SEED", help="Deep niche discovery from a seed term")
    parser.add_argument("--compare", nargs="+", metavar="KW", help="Compare keywords head-to-head")
    parser.add_argument("--shopping", action="store_true", help="Use Google Shopping data")
    parser.add_argument("--geo", default=GEO, help="Country code (default: US)")
    parser.add_argument("--time", default=TIMEFRAME, dest="timeframe",
                        help="Timeframe (default: 'today 12-m')")

    args = parser.parse_args()

    if args.trending:
        cmd_trending(geo=args.geo)
    elif args.discover:
        cmd_discover(args.discover, geo=args.geo, timeframe=args.timeframe)
    elif args.compare:
        cmd_compare(args.compare, geo=args.geo, timeframe=args.timeframe)
    elif args.keywords:
        cmd_research(args.keywords, geo=args.geo, timeframe=args.timeframe,
                     shopping=args.shopping)
    else:
        cmd_interactive()


if __name__ == "__main__":
    main()
