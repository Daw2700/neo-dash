#!/usr/bin/env python3
"""One-off sizing + bundle search for the NEO dashboard (Daniel's ask 2026-07-21).

Per-strategy: max micros tradeable under the 20% 1-yr breach cap, per plan.
Bundles: named sleeve combinations, greedy micro allocation maximizing
survival-adjusted $/mo under the same cap. Tradeify rules are verified
(TRADEIFY_TERMS_2026-07). Apex-150K rules are ASSUMED pending Daniel's
verification (published: $5k trailing threshold, 30% consistency, 90% split
after first $25k) — flagged `assumed` in output.

Writes sizing_results.json next to this file. Engine v2 re-runs this after
every book change.
"""
import json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

MNQ = Path.home() / "mnq_lab"
sys.path.insert(0, str(MNQ))
from gauntlet.account import simulate_account, PLANS

# Apex 150K — ASSUMED (verification pending, decision d-apex-verify)
# Apex 150K — VERIFIED by Daniel 2026-07-22 (apextraderfunding.com screenshot):
# $4,000 EOD trailing drawdown, 50% consistency, payouts each 5 trading days,
# max 20 accounts, 100 micros. Split kept at the global conservative 90%.
# PA daily-loss limit exists but amount unverified -> not modeled as a cushion.
PLANS["apex150"] = dict(buffer=4000, dll=None, consistency=[0.50], gate="cycle5",
                        min_bal_profit=0, caps=[5000, 5000, 5000, 5000],
                        min_payout=500)

BREACH_CAP = 0.20
DEV0, DEV1 = "2022-03-01", "2025-02-28"
CAL = pd.bdate_range(DEV0, DEV1)
VALIDATED = {"b3-monday-long", "b3-preholiday-drift", "b3-nr7-breakout", "b4-open-drive",
             "scan-mbt", "b10-nagel-vix-reversal",
             "mes-gold-overnight-macro-signal-open-continuation"}  # gold-signal in 2026-07-22

CSV = {  # leaderboard id -> data/trades_<x>.csv
    "b2-vix-reversion": "b2_vix", "b3-monday-long": "b3_monday",
    "b3-nr7-breakout": "b3_nr7", "b4-open-drive": "b4_opendrive",
    "b10-nagel-vix-reversal": "b10_nagel", "scan-mbt": "scan_MBT_nr7-orb",
    "b3-preholiday-drift": "b3_prehol", "scan-mcl": "scan_MCL_vix-rebound-long",
    "scan-mym": "scan_MYM_prehol-long", "b3-tom-long": "b3_tom",
    "b3-prior-high-break": "b3_priorhigh", "b7-down-weeks-dip": "b7_downweeks",
    "b3-pm-trend-continuation": "b3_pmtrend", "b7-bond-flight-unwind": "b7_bondflight",
    "8b-biggap-follow": "8b", "rep-bondflight-mes": "rep_bondflight_mes",
    "b2-vol-climax-fade": "b2_climax", "b2-opex-release": "b2_opex",
    "b3-3down-reversion": "b3_3down", "b2-fomc-predrift": "b2_fomcdrift",
    "b2-cpi-follow": "b2_cpi", "b10-fomc-cycle-even": "b10_fomccycle",
    "rep3-vix-mes": "rep3_vix_mes", "rep-nagel-mes": "rep_nagel_mes",
    "b3-month-end-markup": "b3_eom",
    "mes-gold-overnight-macro-signal-open-continuation": "mes-gold-overnight-macro-signal-open-continuation",
}

_daily = {}
def daily(sid):
    if sid not in _daily:
        tr = pd.read_csv(MNQ / f"data/trades_{CSV[sid]}.csv", parse_dates=["date"])
        tr = tr[(tr.date >= DEV0) & (tr.date <= DEV1)]
        _daily[sid] = tr.groupby("date").net.sum().reindex(CAL, fill_value=0.0).values
    return _daily[sid]

def sim(pnl, plan, sims):
    return simulate_account(pnl, plan, sims=sims, rng=np.random.default_rng(7))

_lb = json.loads(Path("data.json").read_text())["leaderboard"]
lb_ids = [r["id"] for r in _lb]
# auto-map any strategy whose worker saved a trades CSV under its own name —
# new graduates join the bundle pool with no manual edit
for _r in _lb:
    if _r["id"] not in CSV and (MNQ / f"data/trades_{_r['id']}.csv").exists():
        CSV[_r["id"]] = _r["id"]
# validated set now follows the leaderboard tier (source of truth: build_data VALID)
VALIDATED = {r["id"] for r in _lb if r.get("tier") == "BOOK SLEEVE"}
t0 = time.time()

# ---------- per-strategy max micros ----------
strategies = {}
for sid in lb_ids:
    if sid not in CSV:
        continue
    d = daily(sid)
    ent = {}
    for plan in ("growth", "apex150"):
        mx = 0
        for m in range(1, 9):
            if sim(d * m, plan, 1200)["p_breach"] <= BREACH_CAP:
                mx = m
            else:
                break
        ent[plan] = {"max_micros": mx}
    strategies[sid] = ent
print(f"strategy sizing done {time.time()-t0:.0f}s: "
      f"{ {s: v['growth']['max_micros'] for s, v in strategies.items()} }")

# ---------- bundle definitions ----------
_ok_tiers = {"BOOK SLEEVE", "candidate"}
have = [r["id"] for r in _lb if r["id"] in CSV and r.get("tier") in _ok_tiers]
val = [s for s in have if s in VALIDATED]
_by = {r["id"]: r for r in _lb}
_auto_rare = [s for s in have if (_by[s].get("n") or 0) < 300 and s not in VALIDATED]
_auto_freq = [s for s in have if (_by[s].get("n") or 0) >= 300]
_best_per_mkt = {}
for s in have:
    mk = _by[s].get("market")
    if mk and (mk not in _best_per_mkt or (_by[s].get("pf") or 0) > (_by[_best_per_mkt[mk]].get("pf") or 0)):
        _best_per_mkt[mk] = s
RARE = [s for s in have if s in ("b2-vix-reversion", "b10-nagel-vix-reversal",
        "b3-preholiday-drift", "scan-mym", "scan-mcl", "b7-down-weeks-dip",
        "b2-opex-release", "b2-vol-climax-fade")]
FREQ = [s for s in have if s in ("b3-monday-long", "b3-nr7-breakout", "b4-open-drive",
        "scan-mbt", "b3-tom-long", "b3-prior-high-break", "b3-pm-trend-continuation",
        "b10-fomc-cycle-even")]
XMKT = [s for s in have if s in ("b3-monday-long", "scan-mbt", "scan-mcl", "scan-mym",
        "b7-bond-flight-unwind", "rep-bondflight-mes", "b2-vix-reversion")]
BUNDLES = [
    ("Validated book (all approved sleeves)", val),
    ("Validated book + vix-reversion", val + ["b2-vix-reversion"]),
    ("Everything (full pool)", have),
    ("Risk-premium core (rare, high WR)", sorted(set(RARE) | set(_auto_rare))[:14]),
    ("Frequent-firing engine", sorted(set(FREQ) | set(_auto_freq))[:14]),
    ("Cross-market spread", sorted(set(XMKT) | set(_best_per_mkt.values()))[:14]),
]

def greedy(members, plan, cap_per=5):
    """Add 1 micro at a time (best (surv$, -breach) addition first) while the
    breach cap holds; keep the best snapshot seen. Payouts often stay $0 until
    the book is big enough, so growth is allowed before surv$ turns positive."""
    micros = {m: 0 for m in members}
    snapshots = []
    while True:
        best = None
        for m in members:
            if micros[m] >= cap_per:
                continue
            trial = sum(daily(s) * q for s, q in micros.items()) + daily(m)
            r = sim(trial, plan, 800)
            if r["p_breach"] <= BREACH_CAP:
                cand = (r["surv_adj_monthly"], -r["p_breach"], m)
                if best is None or cand > best:
                    best = cand
        if best is None:
            break
        micros[best[2]] += 1
        snapshots.append((best[0], dict(micros)))
    if not snapshots:
        return None
    _, micros = max(snapshots, key=lambda s: s[0])
    micros = {m: q for m, q in micros.items() if q}
    # high-precision rescore; shed micros if the tighter estimate breaches the cap
    final = None
    while micros:
        final = sim(sum(daily(s) * q for s, q in micros.items()), plan, 3000)
        if final["p_breach"] <= BREACH_CAP:
            break
        shed = None
        for m in micros:
            trial = {k: v for k, v in {**micros, m: micros[m] - 1}.items() if v}
            if not trial:
                continue
            r = sim(sum(daily(s) * q for s, q in trial.items()), plan, 800)
            cand = (r["p_breach"] <= BREACH_CAP, r["surv_adj_monthly"], m)
            if shed is None or cand > shed:
                shed = cand
        if shed is None:
            return None
        micros[shed[2]] -= 1
        micros = {k: v for k, v in micros.items() if v}
    if not micros or final is None:
        return None
    return {"micros": micros, "p_breach": round(final["p_breach"], 3),
            "usd_mo": round(final["surv_adj_monthly"])}

bundles = []
# Warm start: greedy is order-dependent and not monotone — adding a sleeve can
# steer it to a worse local optimum. Re-evaluate the best-known allocation from
# the previous run and keep whichever solution scores higher today.
try:
    _prev = {b["id"]: b["members"] for b in json.load(open("sizing_results.json")).get("bundles", [])}
except Exception:
    _prev = {}

def _rescore(micros, plan):
    micros = {m: q for m, q in micros.items() if q and m in CSV}
    if not micros:
        return None
    r = sim(sum(daily(s) * q for s, q in micros.items()), plan, 3000)
    if r["p_breach"] > BREACH_CAP:
        return None
    return {"micros": micros, "p_breach": round(r["p_breach"], 3),
            "usd_mo": round(r["surv_adj_monthly"])}

for name, members in BUNDLES:
    for plan, label in (("growth", "tradeify-growth"), ("apex150", "apex150 (verified)")):
        r = greedy(members, plan)
        prev = _prev.get(f"{name}|{plan}")
        if prev and set(prev) <= set(members):
            pr = _rescore(prev, plan)
            if pr and (r is None or pr["usd_mo"] > r["usd_mo"]):
                r = pr
        if r is None:
            continue
        bundles.append({
            "id": f"{name}|{plan}", "name": name, "plan": label,
            "provisional": any(m not in VALIDATED for m in r["micros"]),
            "assumed_rules": False,
            "members": r["micros"], "total_micros": sum(r["micros"].values()),
            "p_breach": r["p_breach"], "usd_mo": r["usd_mo"],
            "usd_mo_5acct": r["usd_mo"] * 5,
            "pct_goal": round(r["usd_mo"] * 5 / 10000, 3)})
        print(f"{time.time()-t0:5.0f}s  {name} [{plan}] -> ${r['usd_mo']}/mo "
              f"breach {r['p_breach']:.1%} {r['micros']}")

# --- per-bundle texture stats: Daniel's priority metrics, computed EVERY refresh ---
from gauntlet.account import SPLIT, WIN_DAY, _consistency_ok

def _first_pay(daily_pnl, plan, years=1, sims=3000, block=10):
    """Faithful extension of gauntlet simulate_account tracking the first payout day."""
    P = PLANS[plan]; rng = np.random.default_rng(7)
    pnl = np.asarray(daily_pnl, float); L = len(pnl); days = int(252 * years)
    first = []
    for s in range(sims):
        idx = np.concatenate([np.arange(i, i + block) % L
                              for i in rng.integers(0, L, days // block + 2)])[:days]
        path = pnl[idx]
        if P.get("dll"): path = np.maximum(path, -P["dll"])
        bal = hw = 0.0; locked = False; day_max = 0.0
        wins = 0; n_pay = 0; cycle_start_bal = 0.0; paid_total = 0.0; fp = None
        for di, d in enumerate(path):
            bal += d
            floor = 100.0 if locked else hw - P["buffer"]
            if bal < floor:
                bal = None; break
            hw = max(hw, bal)
            if not locked and hw > P["buffer"] + 100: locked = True
            day_max = max(day_max, d)
            if d >= WIN_DAY: wins += 1
            room = bal - 2100.0
            w = 0.0; g = P["gate"]
            if room > 0:
                if g == "cycle5" and wins >= 5 and bal > cycle_start_bal:
                    if P.get("caps"):
                        if bal >= P.get("min_bal_profit", 0) and _consistency_ok(P.get("consistency"), n_pay, day_max, bal + paid_total):
                            w = min(P["caps"][min(n_pay, 3)], room)
                    else:
                        w = min(P.get("cap_frac", 1.0) * (bal + paid_total), P.get("cap_abs", 1e9), room)
            if w >= P.get("min_payout", 0) and w > 0:
                if fp is None: fp = di + 1
                bal -= w; paid_total += w; n_pay += 1
                wins = 0; cycle_start_bal = bal; locked = True
        if fp is not None: first.append(fp)
    return (int(np.median(first)) if first else None, round(len(first) / sims, 3))

for b in bundles:
    _pnl = sum(daily(s) * q for s, q in b["members"].items())
    _ser = pd.Series(_pnl, index=CAL)
    _act = _ser[_ser != 0]
    b["wr"] = round(float((_act > 0).mean()), 3) if len(_act) else 0
    _mo = _ser.resample("ME").sum()
    _w, _l = _mo[_mo > 0], _mo[_mo <= 0]
    b["wr_month"] = round(float((_mo > 0).mean()), 3)
    b["months"] = {"win_per_yr": round(len(_w) / len(_mo) * 12, 1),
                   "lose_per_yr": round(len(_l) / len(_mo) * 12, 1),
                   "avg_win": round(float(_w.mean())) if len(_w) else 0,
                   "avg_lose": round(float(_l.mean())) if len(_l) else 0}
    _plan = b["id"].split("|")[1]
    b["first_pay_days"], b["pay_rate_1yr"] = _first_pay(_pnl, _plan)

bundles.sort(key=lambda b: -b["usd_mo"])
Path("sizing_results.json").write_text(json.dumps(
    {"computed": "2026-07-21", "breach_cap": BREACH_CAP, "window": [DEV0, DEV1],
     "strategies": strategies, "bundles": bundles}, indent=1))
print(f"TOTAL {time.time()-t0:.0f}s -> sizing_results.json "
      f"({len(strategies)} strategies, {len(bundles)} bundles)")
