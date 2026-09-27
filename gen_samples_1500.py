"""Generate saved S&P 1500 watchlist samples for all six strategies.
Warms fundamentals_cache.json for new symbols first (takes ~25 min).
Run in background AFTER the bt data build finishes.
Usage: python3 gen_samples_1500.py"""
import json, os, sys
from datetime import date

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
from screener import (fetch_prices, fetch_fundamentals, run_screen, run_fallen_quality,
                      run_profitability, run_momentum, run_profitable_value, run_composite,
                      DEFAULT_PARAMS, FQ_DEFAULTS)

RUNS = [
    ("sample_1500_results.json", "Undiscovered Growth", run_screen, dict(DEFAULT_PARAMS)),
    ("sample_1500_fq_results.json", "Fallen Quality", run_fallen_quality, dict(FQ_DEFAULTS)),
    ("sample_1500_profit_results.json", "Gross Profitability", run_profitability, {"top_n": 100}),
    ("sample_1500_mom_results.json", "Momentum", run_momentum, {"top_n": 100}),
    ("sample_1500_pv_results.json", "Profitable Value", run_profitable_value, {"top_n": 30}),
    ("sample_1500_composite_results.json", "Composite", run_composite, {"top_n": 30}),
]

def main():
    uni = {u["symbol"]: u for u in json.load(open(os.path.join(APP_DIR, "sp1500.json")))}
    symbols = [u["symbol"] for u in json.load(open(os.path.join(APP_DIR, "sp1500.json")))]
    cik_of = {u["symbol"]: u["cik"] for u in json.load(open(os.path.join(APP_DIR, "sp1500.json")))}
    print("fetching prices…", flush=True)
    prices, fails = fetch_prices(symbols)
    print(f"prices ok={len(prices)} fails={len(fails)}", flush=True)
    cpath = os.path.join(APP_DIR, "fundamentals_cache.json")
    cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
    print(f"cache has {len(cache)}, fetching fundamentals…", flush=True)
    funds = fetch_fundamentals(symbols, cik_of, cache,
                               progress=lambda f, t: print(f"  fund {f*100:.0f}% {t}", flush=True) if int(f*20) != int((f-0.001)*20) else None)
    json.dump(funds, open(cpath, "w"))
    print("cache saved", flush=True)
    for fname, strat, fn, params in RUNS:
        top, screened = fn(prices, funds, uni, params)
        watch = [{"news_verdict": "UNREVIEWED", **r} for r in top]
        out = {"run_date": date.today().isoformat(), "strategy": strat, "universe": "S&P 1500",
               "screened": screened, "watchlist": watch, "near_miss": []}
        json.dump(out, open(os.path.join(APP_DIR, fname), "w"))
        print(f"{fname}: {screened} screened, {len(watch)} saved", flush=True)
    print("ALL SAMPLES DONE", flush=True)

if __name__ == "__main__":
    main()
