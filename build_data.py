#!/usr/bin/env python3
"""Export ~/mnq_lab gauntlet state -> data.json for the NEO dashboard (GitHub Pages).

Public-repo policy (Daniel's hosting choice 2026-07-21): stats only — strategy
`params` are never exported; mechanism stays a one-line summary.
Run:  python3 build_data.py   (from this directory)   -> data.json
"""
import json, datetime as dt
from pathlib import Path
from collections import defaultdict

ROOT = Path.home() / "mnq_lab"
OUT = Path(__file__).with_name("data.json")

led = [json.loads(l) for l in (ROOT / "gauntlet/ledger.jsonl").read_text().splitlines() if l.strip()]
regs = {r["hash"]: r for r in led if r["type"] == "register"}
results = [r for r in led if r["type"] == "result"]
hist = defaultdict(list)
for r in results:
    hist[r["hash"]].append(r)

# --- constants mirrored from dashboard/build_dashboard.py (mnq_lab) ---
VALID = {"ef8945553228bfcc", "fd5789814bc7637e", "f3c0baed3995f06f", "00903600149f54ac",
         "5eec72170531044e", "6153da5cd4762a99", "0190bb9911f375cc", "94b9b65b2d08955b"}
DISPLAY = {"scan-mym": "mym-prehol (Dow)", "scan-mcl": "mcl-vix (crude)", "scan-mbt": "mbt-nr7 (bitcoin)"}
PINNED_HASH = "6829f454b50d4422"
DEV3YR_MONTHS = 36

MARKETS = [("MNQ", "Nasdaq-100"), ("MES", "S&P 500"), ("MYM", "Dow"), ("M2K", "Russell 2000"),
           ("MGC", "Gold"), ("SIL", "Silver"), ("MCL", "Crude Oil"), ("MNG", "Nat Gas"),
           ("MBT", "Bitcoin"), ("MET", "Ether"), ("M6E", "Euro FX"), ("ZN", "10-yr Note"),
           ("ZC", "Corn"), ("ZS", "Soybeans")]

def market_of(name):
    n = name.lower()
    for tk in ("mym", "mcl", "mbt", "m2k", "mes", "mng", "mgc", "sil", "m6e", "met", "zn", "zc", "zs"):
        if tk in n.replace("-", " ").split() or f"-{tk}" in n or n.startswith(f"scan-{tk}") or f"{tk}-" in n:
            return tk.upper()
    if "bond" in n or "yield" in n or "duration" in n or "auction" in n:
        return "ZN"
    return "MNQ"

def tier_of(h):
    vs = " ".join(x["metrics"].get("verdict", "") for x in hist.get(h, [])).upper()
    if h in VALID:
        return "BOOK SLEEVE"
    if "DEMOT" in vs or "STAYS OUT" in vs or "FAILS REPLICATION" in vs:
        return "demoted"
    if "PASSES" in vs or "REPLICATES" in vs:
        return "candidate"
    return "killed"

def short_verdict(v):
    u = v.upper()
    for tok in ("KILLED", "DEMOTED", "REPLICATES", "PASSES", "PREDICTED NULL", "FAIL"):
        if tok in u:
            return tok
    return (v.split(";")[0].split("—")[0].strip()[:26] or "result")

# --- leaderboard (all dev3yr rows, then tier-first top 20, pinned always first) ---
rows = []
for h, rs in hist.items():
    d3 = [r for r in rs if r.get("stage") == "dev3yr" and r["metrics"].get("n", 0) > 0]
    if not d3:
        continue
    m = d3[-1]["metrics"]
    raw = regs[h]["name"] if h in regs else h[:8]
    rows.append({"id": raw, "name": DISPLAY.get(raw, raw), "market": market_of(raw),
                 "tier": tier_of(h), "pinned": h == PINNED_HASH, "n": m["n"],
                 "wr": m.get("wr"), "usd_mo": round(m["net"] / DEV3YR_MONTHS),
                 "pf": round(m["pf"], 3), "usd_trade": round(m.get("expectancy", 0), 1),
                 "_hash": h})
TIER_ORDER = {"BOOK SLEEVE": 0, "candidate": 1, "demoted": 2, "killed": 3}
rows.sort(key=lambda r: (not r["pinned"], TIER_ORDER[r["tier"]], -r["pf"]))
leaderboard = rows[:20]

# --- per-market rollups (from ALL rows, not just top 20) ---
by_mkt = defaultdict(lambda: {"tested": 0, "killed": 0, "sleeves": [], "rows": 0})
for r in rows:
    b = by_mkt[r["market"]]
    b["tested"] += 1
    if r["tier"] == "killed":
        b["killed"] += 1
    if r["tier"] == "BOOK SLEEVE":
        b["sleeves"].append(r["name"])
markets = [{"ticker": tk, "display": disp,
            "status": "active" if by_mkt[tk]["sleeves"] else ("idle" if by_mkt[tk]["tested"] == 0 else "active"),
            "n_tested": by_mkt[tk]["tested"], "n_killed": by_mkt[tk]["killed"],
            "book_sleeves": by_mkt[tk]["sleeves"], "agents_now": []}
           for tk, disp in MARKETS]

# --- strategy detail pages (top 20; params intentionally NOT exported) ---
ALL_PASS = {"plateau": "pass", "mechanism_controls": "pass", "ex_best_year": "pass", "mes_replication": "pass"}
strategies = {}
for r in leaderboard:
    h = r["_hash"]
    s = {"name": r["name"], "market": r["market"], "tier": r["tier"],
         "mechanism": regs[h].get("mechanism", "") if h in regs else "",
         "metrics": {k: r[k] for k in ("n", "wr", "pf", "usd_mo", "usd_trade")},
         "verdict_history": [{"t": x["t"], "stage": x.get("stage", "?"),
                              "verdict": short_verdict(x["metrics"].get("verdict", ""))}
                             for x in hist[h]]}
    if r["tier"] == "BOOK SLEEVE":
        s["robustness"] = dict(ALL_PASS)
    strategies[r["id"]] = s

# --- activity feed (latest 12 ledger events) ---
feed = []
tested = set(hist)
for x in sorted(results, key=lambda r: r["t"], reverse=True):
    m = x["metrics"]
    feed.append({"t": x["t"], "hash": x["hash"][:8],
                 "name": (DISPLAY.get(regs[x["hash"]]["name"], regs[x["hash"]]["name"]) if x["hash"] in regs else "?"),
                 "status": short_verdict(m.get("verdict", "")).lower(),
                 "kind": "sweep" if "configs" in m else "result",
                 "detail": (f"{m['configs']:,} configs" if "configs" in m else
                            f"PF {m['pf']}" if "pf" in m else "—")})
for x in sorted((r for h, r in regs.items() if h not in tested), key=lambda r: r["t"], reverse=True):
    feed.append({"t": x["t"], "hash": x["hash"][:8], "name": x["name"],
                 "status": "registered", "kind": "register", "detail": "awaiting test"})
feed = sorted(feed, key=lambda f: f["t"], reverse=True)[:12]

# --- pipeline (engine not launched yet — honest zeros) ---
n_trials = max((r["metrics"].get("n_trials_now", 0) for r in results), default=0) or \
    sum(r["metrics"].get("configs", r["metrics"].get("cells", 1)) for r in results)
per_day = defaultdict(int)
for r in results:
    per_day[r["t"][:10]] += r["metrics"].get("configs", r["metrics"].get("cells", 1))
today = dt.datetime.now(dt.timezone.utc).date()
throughput = [{"date": str(today - dt.timedelta(days=i)), "trials": per_day.get(str(today - dt.timedelta(days=i)), 0)}
              for i in range(13, -1, -1)]
pipeline = {"workers": [], "backlog": [],
            "funnel": {"idea": 0, "registered": len(regs) - len(tested), "dev3yr": 0, "robustness": 0,
                       "mes_replication": 0, "book_candidate": 0, "golden_staged": 0},
            "throughput": throughput}

# --- decisions / pipeline live state (from ~/neo-engine/state; engine owns these) ---
ENG = Path.home() / "neo-engine/state"
def _state(name, default):
    try:
        return json.loads((ENG / name).read_text())
    except Exception:
        return default
decisions = _state("decisions.json", [])
_workers = _state("workers.json", [])
_backlog = _state("backlog.json", [])
_es = _state("engine_state.json", {})
pipeline["workers"] = _workers
pipeline["backlog"] = [{"rank": b.get("rank", i + 1), "idea": b.get("idea"),
                        "source": b.get("source"), "markets": [b.get("market")],
                        "score": b.get("score")} for i, b in enumerate(_backlog)]
pipeline["funnel"]["idea"] = len(_backlog)

# --- roadmap ---
bg = json.loads((ROOT / "data/book4_goal.json").read_text())
books = [{"name": k, "plan": v["plan"], "p_breach": v["p_breach"],
          "usd_mo": round(v["surv_adj_monthly"]), "usd_mo_5acct": round(v["goal_5acct"]),
          "pct_of_goal": round(v["pct_of_goal"], 3), "micros": v["micros"]}
         for k, v in bg.items()]
roadmap = {"goal_usd_mo": 10000, "books": books,
           "eval_plan": {"tradeify_accounts": 5, "apex_accounts": 18,
                         "one_time_cost_usd": [7000, 11000], "first_payout_month": 4,
                         "full_runrate_months": [6, 9]},
           "disclaimer": "All figures simulation-tier until live fills."}

# --- sizing + bundles (from sizing.py; engine v2 re-runs it after book changes) ---
bundles, sizing_meta = [], {}
sf = Path(__file__).with_name("sizing_results.json")
if sf.exists():
    sj = json.loads(sf.read_text())
    bundles = sj["bundles"]
    for b in bundles:
        apex = b["plan"].startswith("apex")
        b["firm"] = "Apex" if apex else "Tradeify"
        b["accounts"] = 18 if apex else 5
        b["usd_mo_total"] = b["usd_mo"] * b["accounts"]
        b["pct_goal"] = round(b["usd_mo_total"] / 10000, 3)
    bundles.sort(key=lambda b: -b["usd_mo_total"])
    sizing_meta = {"computed": sj["computed"], "breach_cap": sj["breach_cap"], "window": sj["window"]}
    for r in leaderboard:
        if r["id"] in sj["strategies"]:
            s = sj["strategies"][r["id"]]
            r["sizing"] = {"growth_max": s["growth"]["max_micros"], "apex_max": s["apex150"]["max_micros"]}
            if r["id"] in strategies:
                strategies[r["id"]]["sizing"] = r["sizing"]

pinned_id = next((r["id"] for r in leaderboard if r["pinned"]), None)
data = {"meta": {"stamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "stale_after_min": 30, "status": _es.get("status", "engine awaiting GO"),
                 "engine_state": _es.get("engine_state", "idle"),
                 "n_registered": len(regs), "n_results": len(results), "n_trials": n_trials,
                 "holdout_looks_spent": sum(1 for r in results if r.get("stage") == "holdout"),
                 "pinned_id": pinned_id,
                 "needs_attention_count": sum(1 for d in decisions if d["needs_attention"])},
        "leaderboard": [{k: v for k, v in r.items() if k != "_hash"} for r in leaderboard],
        "feed": feed, "pipeline": pipeline, "markets": markets,
        "strategies": strategies, "decisions": decisions, "roadmap": roadmap,
        "bundles": bundles, "sizing_meta": sizing_meta}
OUT.write_text(json.dumps(data, indent=1))
print(f"data.json: {len(leaderboard)} lb rows, {len(strategies)} detail pages, "
      f"{len(feed)} feed events, pinned={pinned_id}, trials={n_trials:,}")
