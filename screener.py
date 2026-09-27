"""Undiscovered Growth screener engine: no API keys needed.
- Prices: Yahoo Finance v8 chart API (public, no key)
- Fundamentals: SEC EDGAR companyfacts (public, no key)
- Screen: strong growth + still well below 52-week high + no recent run-up,
  with smaller market caps scored as "less discovered".
"""
import json, math, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

UA_WEB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
UA_SEC = {"User-Agent": "GrowthScreener research@example.com", "Accept-Encoding": "gzip"}
SEC_BASE = "https://data.sec.gov/api/xbrl/companyfacts/"

REV_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueServicesNet", "SalesRevenueGoodsNet"]
GP_TAGS = ["GrossProfit"]
NI_TAGS = ["NetIncomeLoss"]
OCF_TAGS = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment"]
SHARES_TAGS = ["WeightedAverageNumberOfDilutedSharesOutstanding"]
ASSETS_TAGS = ["Assets"]
LIAB_TAGS = ["Liabilities"]

# ---------------- prices ----------------

def yh_closes(sym):
    s = sym.replace(".", "-")
    now = int(time.time())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{s}"
           f"?interval=1d&period1={now - 400 * 86400}&period2={now}")
    req = urllib.request.Request(url, headers=UA_WEB)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.load(r)
        res = d["chart"]["result"][0]
        closes = res["indicators"]["quote"][0]["close"]
        return [c for c in closes if c]
    except Exception:
        return None

def price_stats(sym, closes):
    n = len(closes)
    if n < 120:
        return None
    last = closes[-1]
    hi, lo = max(closes), min(closes)
    mom_12_1 = None
    if n >= 273 and closes[-273]:
        mom_12_1 = round((closes[-22] - closes[-273]) / closes[-273], 4)
    return {
        "symbol": sym, "price": round(last, 2), "high52w": round(hi, 2),
        "low52w": round(lo, 2), "drawdown_52w": round((last - hi) / hi, 4),
        "chg_60d": round((last - (closes[-61] if n >= 61 else closes[0])) / (closes[-61] if n >= 61 else closes[0]), 4),
        "chg_20d": round((last - (closes[-21] if n >= 21 else closes[0])) / (closes[-21] if n >= 21 else closes[0]), 4),
        "mom_12_1": mom_12_1,
        "days_since_high": n - 1 - closes.index(hi), "bars": n,
    }

def fetch_prices(symbols, progress=None):
    out, fails = {}, []
    def one(sym):
        c = yh_closes(sym)
        return (sym, price_stats(sym, c) if c else None)
    with ThreadPoolExecutor(max_workers=10) as ex:
        for i, (sym, s) in enumerate(ex.map(one, symbols)):
            if s:
                out[sym] = s
            else:
                fails.append(sym)
            if progress and (i + 1) % 25 == 0:
                progress((i + 1) / len(symbols), f"Prices: {i + 1}/{len(symbols)}")
            time.sleep(0.02)
    return out, fails

# ---------------- SEC fundamentals ----------------

def sec_get(url):
    import gzip
    req = urllib.request.Request(url, headers=UA_SEC)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass
    return json.loads(raw)

def quarterly_series(facts, tags, unit="USD"):
    for tag in tags:
        try:
            units = facts["facts"]["us-gaap"][tag]["units"][unit]
        except KeyError:
            continue
        pts = []
        for u in units:
            if u.get("form") not in ("10-Q", "10-K"):
                continue
            if u.get("fp") not in ("Q1", "Q2", "Q3", "Q4"):
                continue
            try:
                pts.append((u["end"], float(u["val"])))
            except (KeyError, TypeError):
                pass
        by_end = {}
        for end, val in pts:
            by_end[end] = val
        if len(by_end) >= 8:
            return sorted(by_end.items())
    return []

def quarterly_series_best(facts, tags):
    best, best_ttm = [], 0
    for tag in tags:
        s = quarterly_series(facts, [tag])
        if len(s) >= 8:
            t = sum(v for _, v in s[-4:])
            if t > best_ttm:
                best, best_ttm = s, t
    return best

def ttm(series):
    return sum(v for _, v in series[-4:])

def fundamentals(sym, cik):
    try:
        facts = sec_get(f"{SEC_BASE}CIK{str(cik).zfill(10)}.json")
    except Exception as e:
        return {"symbol": sym, "error": f"sec_fetch: {type(e).__name__}"}
    rev = quarterly_series_best(facts, REV_TAGS)
    gp = quarterly_series(facts, GP_TAGS)
    ni = quarterly_series(facts, NI_TAGS)
    ocf = quarterly_series(facts, OCF_TAGS)
    capex = quarterly_series(facts, CAPEX_TAGS)
    shares = quarterly_series(facts, SHARES_TAGS, unit="shares")
    assets = quarterly_series(facts, ASSETS_TAGS)
    liab = quarterly_series(facts, LIAB_TAGS)
    if len(rev) < 8 or len(ni) < 8:
        return {"symbol": sym, "error": f"insufficient quarterly data (rev={len(rev)}, ni={len(ni)})"}
    ttm_rev, prior_rev = ttm(rev), sum(v for _, v in rev[-8:-4])
    ttm_ni, prior_ni = ttm(ni), sum(v for _, v in ni[-8:-4])
    ttm_gp = ttm(gp) if len(gp) >= 8 else None
    latest_q = rev[-1][1]
    yoy_q = rev[-5][1] if len(rev) >= 5 else None
    ttm_ocf = ttm(ocf) if len(ocf) >= 8 else None
    ttm_capex = ttm(capex) if len(capex) >= 8 else None
    ttm_sh = sum(v for _, v in shares[-4:]) / 4 if len(shares) >= 4 else None
    lev = (liab[-1][1] / assets[-1][1]) if assets and liab and assets[-1][1] else None
    return {
        "symbol": sym,
        "latest_quarter_end": rev[-1][0],
        "ttm_revenue": ttm_rev,
        "ttm_rev_growth": (ttm_rev - prior_rev) / abs(prior_rev) if prior_rev else None,
        "latest_q_rev_yoy": (latest_q - yoy_q) / abs(yoy_q) if yoy_q else None,
        "ttm_net_income": ttm_ni,
        "ttm_ni_growth": (ttm_ni - prior_ni) / abs(prior_ni) if prior_ni else None,
        "ttm_gross_margin": ttm_gp / ttm_rev if ttm_gp and ttm_rev else None,
        "ttm_gross_profit": ttm_gp,
        "total_assets": assets[-1][1] if assets else None,
        "ttm_ocf": ttm_ocf,
        "ttm_fcf": (ttm_ocf - ttm_capex) if (ttm_ocf is not None and ttm_capex is not None) else None,
        "ttm_eps": ttm_ni / ttm_sh if ttm_sh else None,
        "leverage": lev,
    }

def fetch_fundamentals(symbols, cik_of, cache, progress=None, delay=0.15):
    out = {}
    todo = [s for s in symbols if s not in cache]
    for i, sym in enumerate(todo):
        try:
            out[sym] = fundamentals(sym, cik_of[sym])
        except Exception as e:
            out[sym] = {"symbol": sym, "error": f"fetch: {type(e).__name__}"}
        if progress and (i + 1) % 10 == 0:
            progress((i + 1) / max(len(todo), 1), f"Fundamentals: {i + 1}/{len(todo)} (SEC EDGAR)")
        time.sleep(delay)
    cache.update(out)
    return cache

# ---------------- screen ----------------

DEFAULT_PARAMS = {
    "min_rev_growth": 0.10,   # TTM revenue growth >= 10%
    "min_q_yoy": 0.0,         # latest quarter YoY > 0
    "dd_lo": -0.45, "dd_hi": -0.10,  # 10-45% below 52w high
    "max_chg_60d": 0.15,      # no big 60-day run-up
    "max_leverage": 0.85,
    "top_n": 20,
}

def run_screen(prices, funds, uni, params=None):
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)
    cands = []
    for sym, f in funds.items():
        if sym not in prices or "error" in f:
            continue
        pr = prices[sym]
        g, q = f.get("ttm_rev_growth"), f.get("latest_q_rev_yoy")
        ni_ttm, fcf, lev = f.get("ttm_net_income"), f.get("ttm_fcf"), f.get("leverage")
        dd, c60 = pr["drawdown_52w"], pr["chg_60d"]
        if not (g is not None and g >= p["min_rev_growth"]): continue
        if not (q is not None and q > p["min_q_yoy"]): continue
        if not (ni_ttm and ni_ttm > 0): continue
        if not (fcf and fcf > 0): continue
        if lev is not None and lev >= p["max_leverage"]: continue
        if not (p["dd_lo"] <= dd <= p["dd_hi"]): continue
        if c60 is None or c60 >= p["max_chg_60d"]: continue
        eps = f.get("ttm_eps")
        shares = ni_ttm / eps if (eps and eps > 0) else None
        mcap = pr["price"] * shares if shares else None
        if not mcap or mcap <= 0: continue
        growth_score = 0.5 * g + 0.3 * q + 0.2 * min(f.get("ttm_ni_growth") or 0, 2.0)
        fcf_margin = fcf / f["ttm_revenue"] if f.get("ttm_revenue") else 0
        growth_score += 0.1 * min(max(fcf_margin, 0), 0.5)
        score = round(growth_score * (13 - math.log10(mcap)) * (1 + abs(dd)), 4)
        cands.append({
            "symbol": sym, "name": uni[sym]["name"], "sector": uni[sym]["sector"],
            "price": pr["price"], "high52w": pr["high52w"],
            "drawdown_52w": round(dd, 4), "chg_60d": round(c60, 4),
            "mcap_bn": round(mcap / 1e9, 2),
            "ttm_rev_growth": round(g, 4), "latest_q_rev_yoy": round(q, 4),
            "ttm_ni_growth": round(f["ttm_ni_growth"], 4) if f.get("ttm_ni_growth") is not None else None,
            "ttm_gross_margin": round(f["ttm_gross_margin"], 4) if f.get("ttm_gross_margin") else None,
            "leverage": round(lev, 3) if lev else None,
            "growth_score": round(growth_score, 4), "score": score,
        })
    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands[:p["top_n"]], len(cands)

# ---------------- fallen quality screen ----------------

FQ_DEFAULTS = {"min_bars": 200, "min_drawdown": 0.25, "min_chg_60d": -0.10, "top_n": 50}

def fq_health_checks(f, sector):
    """Mirror of the daily scan's health verdict. Returns dict of check->bool."""
    g, q = f.get("ttm_rev_growth"), f.get("latest_q_rev_yoy")
    ni, ni_g = f.get("ttm_net_income"), f.get("ttm_ni_growth")
    gm, lev = f.get("ttm_gross_margin"), f.get("leverage")
    ocf, fcf, rev = f.get("ttm_ocf"), f.get("ttm_fcf"), f.get("ttm_revenue")
    if sector in ("Real Estate", "Utilities"):
        lev_ok = lev is None or lev < 0.97 or (fcf is not None and fcf > 0)
    else:
        lev_ok = lev is None or lev < 0.90 or (fcf is not None and fcf > 0)
    return {
        "rev_ttm_ok": g is not None and g >= -0.05,
        "rev_latest_q_ok": q is not None and q >= -0.05,
        "profitable": ni is not None and ni > 0,
        "ni_not_collapsed": ni_g is not None and ni_g >= -0.40,
        "margin_stable": True,  # needs prior margin; checked in full pipeline
        "ocf_positive": ocf is not None and ocf > 0,
        "leverage_ok": lev_ok,
        "big_enough": rev is not None and rev >= 1e9,
    }

def run_fallen_quality(prices, funds, uni, params=None):
    p = dict(FQ_DEFAULTS)
    if params:
        p.update(params)
    ranked, nearmiss = [], []
    for sym, f in funds.items():
        if sym not in prices or "error" in f:
            continue
        pr = prices[sym]
        if pr.get("bars", 0) < p["min_bars"]:
            continue
        dd, c60 = pr["drawdown_52w"], pr["chg_60d"]
        if not (dd <= -p["min_drawdown"] and c60 is not None and c60 <= p["min_chg_60d"]):
            continue
        eps = f.get("ttm_eps")
        pe = pr["price"] / eps if eps and eps > 0 else None
        rec = {"symbol": sym, "name": uni[sym]["name"], "sector": uni[sym]["sector"],
               "price": pr["price"], "high52w": pr["high52w"],
               "drawdown_52w": round(dd, 4), "chg_60d": round(c60, 4),
               "chg_20d": round(pr.get("chg_20d", 0), 4),
               "days_since_high": pr.get("days_since_high"),
               "ttm_revenue": f.get("ttm_revenue"),
               "ttm_rev_growth": round(f["ttm_rev_growth"], 4) if f.get("ttm_rev_growth") is not None else None,
               "latest_q_rev_yoy": round(f["latest_q_rev_yoy"], 4) if f.get("latest_q_rev_yoy") is not None else None,
               "ttm_net_income": f.get("ttm_net_income"),
               "ttm_ni_growth": round(f["ttm_ni_growth"], 4) if f.get("ttm_ni_growth") is not None else None,
               "ttm_gross_margin": round(f["ttm_gross_margin"], 4) if f.get("ttm_gross_margin") else None,
               "ttm_ocf": f.get("ttm_ocf"), "ttm_fcf": f.get("ttm_fcf"),
               "ttm_eps": round(eps, 2) if eps else None,
               "pe_ttm": round(pe, 1) if pe else None,
               "leverage": round(f["leverage"], 3) if f.get("leverage") else None}
        checks = fq_health_checks(f, uni[sym]["sector"])
        if all(checks.values()):
            g = f.get("ttm_rev_growth") or 0
            rec["score"] = round(abs(dd) * (1 + max(g, -0.05)), 3)
            ranked.append(rec)
        else:
            rec["failed"] = [k for k, v in checks.items() if not v]
            nearmiss.append(rec)
    ranked.sort(key=lambda r: r["score"], reverse=True)
    nearmiss.sort(key=lambda r: r["drawdown_52w"])
    return ranked[:p["top_n"]], nearmiss

# ---------------- gross profitability (Novy-Marx) ----------------

def _mcap(pr, f):
    eps, ni = f.get("ttm_eps"), f.get("ttm_net_income")
    if eps and eps > 0 and ni:
        return pr["price"] * (ni / eps)
    return None

def run_profitability(prices, funds, uni, params=None):
    p = {"top_n": 100}
    p.update(params or {})
    rows = []
    for sym, f in funds.items():
        if sym not in prices or "error" in f:
            continue
        gp, ta = f.get("ttm_gross_profit"), f.get("total_assets")
        if not gp or not ta or gp <= 0 or ta <= 0:
            continue
        gpa = gp / ta
        mcap = _mcap(prices[sym], f)
        rows.append({
            "symbol": sym, "name": uni[sym]["name"], "sector": uni[sym]["sector"],
            "price": prices[sym]["price"],
            "mcap_bn": round(mcap / 1e9, 2) if mcap else None,
            "gp_a": round(gpa, 4), "score": round(gpa, 4),
        })
    rows.sort(key=lambda r: r["gp_a"], reverse=True)
    return rows[:p["top_n"]], len(rows)

# ---------------- momentum 12-1 (Jegadeesh-Titman) ----------------

def run_momentum(prices, funds, uni, params=None):
    p = {"top_n": 100}
    p.update(params or {})
    rows = []
    for sym, pr in prices.items():
        if sym not in uni:
            continue
        m = pr.get("mom_12_1")
        if m is None:
            continue
        mcap = _mcap(pr, funds.get(sym, {}))
        rows.append({
            "symbol": sym, "name": uni[sym]["name"], "sector": uni[sym]["sector"],
            "price": pr["price"],
            "mcap_bn": round(mcap / 1e9, 2) if mcap else None,
            "mom_12_1": m, "score": m,
        })
    rows.sort(key=lambda r: r["mom_12_1"], reverse=True)
    return rows[:p["top_n"]], len(rows)

# ---------------- profitable value (Magic-Formula style) ----------------

def run_profitable_value(prices, funds, uni, params=None):
    p = {"top_n": 30}
    p.update(params or {})
    cands = []
    for sym, f in funds.items():
        if sym not in prices or "error" in f:
            continue
        if uni[sym]["sector"] == "Financials":
            continue
        pr = prices[sym]
        gp, ta = f.get("ttm_gross_profit"), f.get("total_assets")
        lev = f.get("leverage")
        eps, fcf = f.get("ttm_eps"), f.get("ttm_fcf")
        if not gp or not ta or gp <= 0 or ta <= 0:
            continue
        if lev is None:
            continue
        mcap = _mcap(pr, f)
        if not mcap or mcap <= 0:
            continue
        book = ta * (1 - lev)
        if book <= 0:
            continue
        if not eps or eps <= 0 or not fcf or fcf <= 0:
            continue
        cands.append({
            "symbol": sym, "name": uni[sym]["name"], "sector": uni[sym]["sector"],
            "price": pr["price"], "mcap_bn": round(mcap / 1e9, 2),
            "bm": round(book / mcap, 4), "ep": round(eps / pr["price"], 4),
            "fcfy": round(fcf / mcap, 4), "gp_a": round(gp / ta, 4),
        })
    for key in ("bm", "ep", "fcfy", "gp_a"):
        for i, r in enumerate(sorted(cands, key=lambda r: r[key], reverse=True)):
            r[key + "_rank"] = i + 1
    for r in cands:
        r["value_rank"] = round((r["bm_rank"] + r["ep_rank"] + r["fcfy_rank"]) / 3, 1)
        r["combined"] = r["value_rank"] + r["gp_a_rank"]
        r["score"] = round(r["combined"], 1)
    cands.sort(key=lambda r: r["combined"])
    return cands[:p["top_n"]], len(cands)

# ---------------- composite (all-rounder) ----------------

def run_composite(prices, funds, uni, params=None):
    """Stocks that rank well on ALL the factor screens at once:
    value (B/M, E/P, FCF yield), quality (GP/assets), momentum (12-1),
    growth (TTM revenue growth). Ex-financials; must be profitable with positive FCF."""
    p = {"top_n": 30}
    p.update(params or {})
    cands = []
    for sym, f in funds.items():
        if sym not in prices or "error" in f:
            continue
        if uni[sym]["sector"] == "Financials":
            continue
        pr = prices[sym]
        gp, ta = f.get("ttm_gross_profit"), f.get("total_assets")
        lev = f.get("leverage")
        eps, fcf = f.get("ttm_eps"), f.get("ttm_fcf")
        ni = f.get("ttm_net_income")
        mom = pr.get("mom_12_1")
        g = f.get("ttm_rev_growth")
        if not gp or not ta or gp <= 0 or ta <= 0:
            continue
        if lev is None:
            continue
        mcap = _mcap(pr, f)
        if not mcap or mcap <= 0:
            continue
        book = ta * (1 - lev)
        if book <= 0:
            continue
        if not eps or eps <= 0 or not fcf or fcf <= 0:
            continue
        if not ni or ni <= 0:
            continue
        if mom is None or g is None:
            continue
        cands.append({
            "symbol": sym, "name": uni[sym]["name"], "sector": uni[sym]["sector"],
            "price": pr["price"], "mcap_bn": round(mcap / 1e9, 2),
            "bm": round(book / mcap, 4), "ep": round(eps / pr["price"], 4),
            "fcfy": round(fcf / mcap, 4), "gp_a": round(gp / ta, 4),
            "mom_12_1": round(mom, 4), "ttm_rev_growth": round(g, 4),
        })
    for key in ("bm", "ep", "fcfy", "gp_a", "mom_12_1", "ttm_rev_growth"):
        for i, r in enumerate(sorted(cands, key=lambda r: r[key], reverse=True)):
            r[key + "_rank"] = i + 1
    for r in cands:
        r["value_rank"] = round((r["bm_rank"] + r["ep_rank"] + r["fcfy_rank"]) / 3, 1)
        r["combined"] = r["value_rank"] + r["gp_a_rank"] + r["mom_12_1_rank"] + r["ttm_rev_growth_rank"]
        r["score"] = round(r["combined"], 1)
    cands.sort(key=lambda r: r["combined"])
    return cands[:p["top_n"]], len(cands)
