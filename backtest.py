"""Point-in-time monthly backtests for the six strategies.
Data (precomputed, bundled with the app):
  data_price.json   - monthly adjusted closes, 52w high, 60d change (Yahoo)
  data_fund_v2.json - monthly point-in-time fundamentals (SEC EDGAR, filed-date honest)
Caveats shown in the UI: current S&P 500 constituents only (survivorship bias),
monthly granularity, no transaction costs, equal weight, long only.
Methodology notes: Sharpe ratios assume a 0% risk-free rate. Months with no
eligible holdings are scored as cash (0%). Annual strategies (June formation)
start only after their first June portfolio is formed - the pre-formation
months are excluded from both the strategy and the SPY benchmark series.
"""
import json, math, os

APP_DIR = os.path.dirname(os.path.abspath(__file__))

_price = None
_fund = None
_pxm = {}   # sym -> {ym: idx into that sym's arrays}
_fmi = {}   # fund ym -> idx
_spym = {}

def load():
    global _price, _fund
    if _price is None:
        _price = json.load(open(os.path.join(APP_DIR, "data_price.json")))
        _fund = json.load(open(os.path.join(APP_DIR, "data_fund_v2.json")))
        for sym, f in _price["symbols"].items():
            _pxm[sym] = {ym: i for i, ym in enumerate(f["m"])}
        for i, ym in enumerate(_fund["months"]):
            _fmi[ym] = i
        spy = _price["spy"]
        for i, ym in enumerate(spy["m"]):
            _spym[ym] = i
    return _price, _fund

def _close(sym, ym):
    i = _pxm.get(sym, {}).get(ym)
    if i is None:
        return None
    return _price["symbols"][sym]["c"][i]

def _pfeat(sym, ym, key):
    i = _pxm.get(sym, {}).get(ym)
    if i is None:
        return None
    return _price["symbols"][sym][key][i]

def _f(sym, field, ym):
    i = _fmi.get(ym)
    if i is None:
        return None
    arr = _fund["symbols"].get(sym, {}).get(field)
    if not arr or i >= len(arr):
        return None
    return arr[i]

def _drawdown(sym, ym):
    c, h = _close(sym, ym), _pfeat(sym, ym, "h")
    if not c or not h:
        return None
    return c / h - 1

def _chg60(sym, ym):
    return _pfeat(sym, ym, "d")

# ---------------- screens (as of month ym) ----------------

def screen_momentum(ym, uni, top_n):
    load()
    rows = []
    for sym in uni:
        i = _pxm.get(sym, {}).get(ym)
        if i is None or i < 13:
            continue
        c = _price["symbols"][sym]["c"]
        if not c[i - 1] or not c[i - 13]:
            continue
        rows.append((sym, c[i - 1] / c[i - 13] - 1))
    rows.sort(key=lambda r: r[1], reverse=True)
    return [s for s, _ in rows[:top_n]]

def screen_profitability(ym, uni, top_n):
    load()
    rows = []
    for sym in uni:
        gpa = _f(sym, "gpa", ym)
        if gpa is None or gpa <= 0:
            continue
        rows.append((sym, gpa))
    rows.sort(key=lambda r: r[1], reverse=True)
    return [s for s, _ in rows[:top_n]]

def screen_profitable_value(ym, uni, top_n):
    load()
    cands = []
    for sym, u in uni.items():
        if u["sector"] == "Financials":
            continue
        c = _close(sym, ym)
        sh, book = _f(sym, "sh", ym), _f(sym, "book", ym)
        ni, fcf = _f(sym, "ni", ym), _f(sym, "fcf", ym)
        gpa = _f(sym, "gpa", ym)
        if not c or not sh or not book or book <= 0:
            continue
        if not ni or ni <= 0 or not fcf or fcf <= 0:
            continue
        if not gpa or gpa <= 0:
            continue
        mcap = c * sh
        cands.append({"sym": sym, "bm": book / mcap, "ep": ni / mcap,
                      "fcfy": fcf / mcap, "gpa": gpa})
    for key in ("bm", "ep", "fcfy", "gpa"):
        for i, r in enumerate(sorted(cands, key=lambda r: r[key], reverse=True)):
            r[key + "_rank"] = i + 1
    for r in cands:
        r["score"] = (r["bm_rank"] + r["ep_rank"] + r["fcfy_rank"]) / 3 + r["gpa_rank"]
    cands.sort(key=lambda r: r["score"])
    return [r["sym"] for r in cands[:top_n]]

def screen_composite(ym, uni, top_n):
    """All-rounder: rank on value (B/M, E/P, FCF yield), quality (GP/A),
    momentum (12-1) and growth (TTM rev growth); ex-financials; profitable + FCF>0."""
    load()
    cands = []
    for sym, u in uni.items():
        if u["sector"] == "Financials":
            continue
        c = _close(sym, ym)
        sh, book = _f(sym, "sh", ym), _f(sym, "book", ym)
        ni, fcf = _f(sym, "ni", ym), _f(sym, "fcf", ym)
        gpa = _f(sym, "gpa", ym)
        rg = _f(sym, "rg", ym)
        i = _pxm.get(sym, {}).get(ym)
        mom = None
        if i is not None and i >= 13:
            cc = _price["symbols"][sym]["c"]
            if cc[i - 1] and cc[i - 13]:
                mom = cc[i - 1] / cc[i - 13] - 1
        if not c or not sh or not book or book <= 0:
            continue
        if not ni or ni <= 0 or not fcf or fcf <= 0:
            continue
        if not gpa or gpa <= 0:
            continue
        if rg is None or mom is None:
            continue
        mcap = c * sh
        cands.append({"sym": sym, "bm": book / mcap, "ep": ni / mcap,
                      "fcfy": fcf / mcap, "gpa": gpa, "mom": mom, "rg": rg})
    for key in ("bm", "ep", "fcfy", "gpa", "mom", "rg"):
        for i, r in enumerate(sorted(cands, key=lambda r: r[key], reverse=True)):
            r[key + "_rank"] = i + 1
    for r in cands:
        r["score"] = ((r["bm_rank"] + r["ep_rank"] + r["fcfy_rank"]) / 3
                      + r["gpa_rank"] + r["mom_rank"] + r["rg_rank"])
    cands.sort(key=lambda r: r["score"])
    return [r["sym"] for r in cands[:top_n]]

def _lev_ok(sym, ym):
    load()
    lev, fcf = _f(sym, "lev", ym), _f(sym, "fcf", ym)
    return lev is None or lev < 0.90 or (fcf is not None and fcf > 0)

def screen_fallen_quality(ym, uni, top_n):
    load()
    rows = []
    for sym, u in uni.items():
        dd, c60 = _drawdown(sym, ym), _chg60(sym, ym)
        if dd is None or c60 is None or not (dd <= -0.25 and c60 <= -0.10):
            continue
        rg, qy = _f(sym, "rg", ym), _f(sym, "qy", ym)
        ni, nig = _f(sym, "ni", ym), _f(sym, "nig", ym)
        ocf, gmd = _f(sym, "ocf", ym), _f(sym, "gmd", ym)
        rev = _f(sym, "rev", ym)
        if rg is None or rg < -0.05: continue
        if qy is None or qy < -0.05: continue
        if not ni or ni <= 0: continue
        if nig is None or nig < -0.40: continue
        if gmd is not None and gmd < -0.03: continue
        if not ocf or ocf <= 0: continue
        if not _lev_ok(sym, ym): continue
        if not rev or rev < 1e9: continue
        rows.append((sym, abs(dd) * (1 + max(rg, -0.05))))
    rows.sort(key=lambda r: r[1], reverse=True)
    return [s for s, _ in rows[:top_n]]

def screen_growth(ym, uni, top_n):
    load()
    rows = []
    for sym in uni:
        dd, c60 = _drawdown(sym, ym), _chg60(sym, ym)
        if dd is None or c60 is None or not (-0.45 <= dd <= -0.10) or c60 >= 0.15:
            continue
        rg, qy = _f(sym, "rg", ym), _f(sym, "qy", ym)
        ni, fcf = _f(sym, "ni", ym), _f(sym, "fcf", ym)
        lev = _f(sym, "lev", ym)
        if rg is None or rg < 0.10: continue
        if qy is None or qy <= 0: continue
        if not ni or ni <= 0: continue
        if not fcf or fcf <= 0: continue
        if lev is not None and lev >= 0.85: continue
        rows.append((sym, rg * (1 + abs(dd))))
    rows.sort(key=lambda r: r[1], reverse=True)
    return [s for s, _ in rows[:top_n]]

SCREENS = {
    "🌱 Undiscovered Growth": (screen_growth, "monthly", 20),
    "📉 Fallen Quality": (screen_fallen_quality, "monthly", 50),
    "💰 Gross Profitability": (screen_profitability, "annual", 100),
    "🚀 Momentum": (screen_momentum, "monthly", 100),
    "⚖️ Profitable Value": (screen_profitable_value, "annual", 30),
    "🎯 Composite": (screen_composite, "monthly", 30),
}

# ---------------- simulator ----------------

def _is_rebalance(ym, freq, months):
    if freq == "monthly":
        return True
    return ym.endswith("-06")  # annual: end of June

def run_backtest(strategy, uni, start_ym="2017-01", top_n=None):
    load()
    screen, freq, default_n = SCREENS[strategy]
    top_n = top_n or default_n
    months = [m for m in _fund["months"] if m >= start_ym and m in _spym]
    if not months:
        return {"error": "no months in range"}
    holdings = []
    strat_rets, spy_rets, labels = [], [], []
    prev_hold = []
    formed = False  # no returns recorded before the first portfolio exists
    for k, ym in enumerate(months):
        if _is_rebalance(ym, freq, months):
            holdings = screen(ym, uni, top_n)
            if not formed:
                # first portfolio just formed at end of this month; it starts
                # earning next month, so skip recording a return for this month
                formed = True
                prev_hold = holdings
                continue
        if k == 0 or not formed:
            prev_hold = holdings
            continue
        pm = months[k - 1]
        si = _spym[ym]; si0 = _spym[pm]
        spyc, spyc0 = _price["spy"]["c"][si], _price["spy"]["c"][si0]
        if not (spyc and spyc0):
            prev_hold = holdings
            continue
        rets = []
        for s in prev_hold:
            c, c0 = _close(s, ym), _close(s, pm)
            if c and c0:
                rets.append(c / c0 - 1)
        # no eligible holdings -> cash (0%), never a skipped month
        strat_rets.append(sum(rets) / len(rets) if rets else 0.0)
        spy_rets.append(spyc / spyc0 - 1)
        labels.append(ym)
        prev_hold = holdings
    return _metrics(labels, strat_rets, spy_rets, holdings)

def _metrics(labels, sr, br, last_holdings):
    import math
    def curve(rets):
        c, out = 1.0, []
        for r in rets:
            c *= (1 + r)
            out.append(c)
        return out
    def cagr(rets, n_months):
        if not rets or n_months <= 0:
            return None
        tot = math.prod(1 + r for r in rets) - 1
        return (1 + tot) ** (12 / n_months) - 1
    def sharpe(rets):
        if len(rets) < 12:
            return None
        mu = sum(rets) / len(rets)
        var = sum((r - mu) ** 2 for r in rets) / len(rets)
        return (mu / math.sqrt(var) * math.sqrt(12)) if var > 1e-12 else None
    def maxdd(curve_):
        peak, md = curve_[0], 0.0
        for c in curve_:
            peak = max(peak, c)
            md = min(md, c / peak - 1)
        return md
    sc, bc = curve(sr), curve(br)
    yearly = {}
    for ym, r, b in zip(labels, sr, br):
        y = yearly.setdefault(ym[:4], {"s": [], "b": []})
        y["s"].append(r); y["b"].append(b)
    yearly = {y: {"strat": round(math.prod(1 + r for r in v["s"]) - 1, 4),
                  "spy": round(math.prod(1 + r for r in v["b"]) - 1, 4)}
              for y, v in sorted(yearly.items())}
    n = len(sr)
    return {
        "months": labels,
        "strat_curve": [round(c, 4) for c in sc],
        "spy_curve": [round(c, 4) for c in bc],
        "strat_cagr": None if cagr(sr, n) is None else round(cagr(sr, n), 4),
        "spy_cagr": None if cagr(br, n) is None else round(cagr(br, n), 4),
        "strat_sharpe": None if sharpe(sr) is None else round(sharpe(sr), 2),
        "spy_sharpe": None if sharpe(br) is None else round(sharpe(br), 2),
        "strat_maxdd": round(maxdd(sc), 4) if sc else None,
        "spy_maxdd": round(maxdd(bc), 4) if bc else None,
        "strat_total": round(sc[-1] - 1, 4) if sc else None,
        "spy_total": round(bc[-1] - 1, 4) if bc else None,
        "n_months": n,
        "yearly": yearly,
        "last_holdings": last_holdings,
    }
