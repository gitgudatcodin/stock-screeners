"""Six-strategy stock screener — Streamlit app. No API keys needed.
Run: pip install -r requirements.txt && streamlit run app.py
"""
import json, os
import pandas as pd
import streamlit as st

from screener import (fetch_prices, fetch_fundamentals, run_screen,
                      run_fallen_quality, run_profitability, run_momentum,
                      run_profitable_value, run_composite,
                      DEFAULT_PARAMS, FQ_DEFAULTS)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(APP_DIR, "fundamentals_cache.json")
VERDICT_EMOJI = {"CLEAR": "🟢", "CAUTION": "🟡", "REJECT": "🔴", "UNREVIEWED": "⚪"}

UNIVERSES = {"S&P 500": "sp500.json", "S&P 1500": "sp1500.json"}

def load_uni(name):
    return {u["symbol"]: u for u in json.load(open(os.path.join(APP_DIR, UNIVERSES[name])))}

def _verdict(df):
    df["verdict"] = df["news_verdict"].map(lambda v: f"{VERDICT_EMOJI.get(v, '')} {v}")
    return df

def _pct(df, col, label=None):
    df[label or col] = (df[col] * 100).round(1).astype(str) + "%"
    return df

# ---------- per-strategy config ----------

def _growth_params():
    c1, c2, c3 = st.columns(3)
    min_rev = c1.slider("Min TTM revenue growth", 0.0, 0.50, DEFAULT_PARAMS["min_rev_growth"], 0.05, format="%.0f%%")
    dd_hi = c2.slider("Must be at least this far below 52w high", 0.02, 0.30, 0.10, 0.01, format="%.0f%%")
    dd_lo = c3.slider("Deepest drawdown allowed", 0.30, 0.70, 0.45, 0.05, format="%.0f%%")
    c4, c5, c6 = st.columns(3)
    max_60d = c4.slider("Max 60-day run-up", 0.05, 0.50, DEFAULT_PARAMS["max_chg_60d"], 0.05, format="%.0f%%")
    max_lev = c5.slider("Max leverage", 0.5, 1.0, DEFAULT_PARAMS["max_leverage"], 0.05)
    top_n = c6.slider("Top N", 5, 50, DEFAULT_PARAMS["top_n"], 5)
    return {"min_rev_growth": min_rev, "dd_hi": -dd_hi, "dd_lo": -dd_lo,
            "max_chg_60d": max_60d, "max_leverage": max_lev, "top_n": top_n}

def _growth_frame(rows):
    df = _verdict(pd.DataFrame(rows))
    _pct(df, "ttm_rev_growth", "rev_growth"); _pct(df, "latest_q_rev_yoy", "q_yoy")
    _pct(df, "drawdown_52w", "below_high"); _pct(df, "chg_60d", "60d")
    cols = ["verdict", "symbol", "name", "sector", "price"]
    if "mcap_bn" in df.columns:
        cols.append("mcap_bn")
    return df[cols + ["rev_growth", "q_yoy", "below_high", "60d", "score"]]

def _fq_params():
    c1, c2, c3 = st.columns(3)
    min_dd = c1.slider("Min drawdown from 52w high", 0.15, 0.50, FQ_DEFAULTS["min_drawdown"], 0.05, format="%.0f%%")
    max_60d = c2.slider("Max 60-day change (must be down at least this much)",
                        -0.30, 0.0, FQ_DEFAULTS["min_chg_60d"], 0.05, format="%.0f%%")
    top_n = c3.slider("Top N", 5, 60, FQ_DEFAULTS["top_n"], 5)
    return {"min_drawdown": min_dd, "min_chg_60d": max_60d, "top_n": top_n}

def _profit_params():
    top_n = st.slider("Top N by gross profitability", 20, 200, 100, 10)
    return {"top_n": top_n}

def _profit_frame(rows):
    df = _verdict(pd.DataFrame(rows))
    _pct(df, "gp_a", "GP/A")
    cols = ["verdict", "symbol", "name", "sector", "price"]
    if "mcap_bn" in df.columns:
        cols.append("mcap_bn")
    return df[cols + ["GP/A", "score"]]

def _mom_params():
    top_n = st.slider("Top N by 12-1 momentum", 20, 200, 100, 10)
    return {"top_n": top_n}

def _mom_frame(rows):
    df = _verdict(pd.DataFrame(rows))
    _pct(df, "mom_12_1", "12-1 return")
    cols = ["verdict", "symbol", "name", "sector", "price"]
    if "mcap_bn" in df.columns:
        cols.append("mcap_bn")
    return df[cols + ["12-1 return", "score"]]

def _pv_params():
    top_n = st.slider("Portfolio size", 10, 50, 30, 5)
    return {"top_n": top_n}

def _pv_frame(rows):
    df = _verdict(pd.DataFrame(rows))
    return df[["verdict", "symbol", "name", "sector", "price", "mcap_bn",
               "value_rank", "gp_a_rank", "combined", "score"]].rename(
        columns={"gp_a_rank": "quality_rank"})

def _composite_params():
    top_n = st.slider("Portfolio size", 10, 50, 30, 5)
    return {"top_n": top_n}

def _composite_frame(rows):
    df = _verdict(pd.DataFrame(rows))
    return df[["verdict", "symbol", "name", "sector", "price", "mcap_bn",
               "value_rank", "gp_a_rank", "mom_12_1_rank", "ttm_rev_growth_rank",
               "combined", "score"]].rename(
        columns={"gp_a_rank": "quality_rank", "mom_12_1_rank": "momentum_rank",
                 "ttm_rev_growth_rank": "growth_rank"})

def _detail_growth(w):
    gm = w.get("ttm_gross_margin")
    return (f"Price ${w['price']} | 52w high ${w['high52w']} | "
            f"Gross margin {f'{gm:.1%}' if gm else 'n/a'} | Leverage {w.get('leverage') or 'n/a'}")

def _detail_simple(w):
    extra = ""
    if w.get("gp_a") is not None: extra += f" | GP/A {w['gp_a']:.1%}"
    if w.get("mom_12_1") is not None: extra += f" | 12-1 return {w['mom_12_1']:.1%}"
    if w.get("combined") is not None:
        extra += f" | value rank {w['value_rank']}, quality rank {w['gp_a_rank']}"
    return f"Price ${w['price']}{extra}"

STRATEGIES = {
    "🌱 Undiscovered Growth": {
        "sample": "sample_results.json",
        "sample1500": "sample_1500_results.json",
        "blurb": "Strong growers the market hasn't noticed yet — SEC fundamentals + price position.",
        "run": run_screen, "params": _growth_params, "frame": _growth_frame, "detail": _detail_growth,
        "how": """**Undiscovered Growth** — great growth that hasn't caught attention or shot up yet:
1. **Growth (SEC EDGAR):** TTM revenue growth ≥ 10% (adjustable), latest quarter growing YoY, positive TTM net income and free cash flow.
2. **Hasn't shot up (price):** 10–45% below the 52-week high, no 60-day run-up over 15%.
3. **Quality gate:** leverage under 0.85.
4. **"Undiscovered" tilt:** smaller market caps score higher — the crowd finds big caps first.
Score = growth × size discount × distance-from-high.""",
    },
    "📉 Fallen Quality": {
        "sample": "sample_fq_results.json",
        "sample1500": "sample_1500_fq_results.json",
        "blurb": "Quality stocks with large price declines but no fundamental change.",
        "run": run_fallen_quality, "params": _fq_params, "frame": _growth_frame, "detail": _detail_growth,
        "how": """**Fallen Quality** — quality stocks with large price declines but no fundamental change:
1. **Price screen:** ≥ 200 trading days, ≥ 25% below the 52-week high, ≥ 10% down over 60 trading days.
2. **Fundamentals intact (SEC EDGAR):** TTM and latest-quarter revenue not down more than 5%, profitable, net income not collapsed (> -40%), gross margin stable, operating cash flow positive, leverage sane (looser bar for REITs/utilities), revenue ≥ $1B.
3. **News veto:** names with a fundamental problem (fraud, distress, broken thesis) are excluded as REJECTs.
Score = drawdown × (1 + revenue growth).""",
    },
    "💰 Gross Profitability": {
        "sample": "sample_profit_results.json",
        "sample1500": "sample_1500_profit_results.json",
        "blurb": "Novy-Marx (2013): the most profitable companies keep winning — gross profit ÷ total assets.",
        "run": run_profitability, "params": _profit_params, "frame": _profit_frame, "detail": _detail_simple,
        "how": """**Gross Profitability** (Novy-Marx, 2013, "The Other Side of Value"):
Rank the universe by **gross profit ÷ total assets**, buy the top ~100 equal-weight, rebalance annually.
Gross profitability predicts returns about as well as value does — and it works specifically among large caps.
Low turnover, defensive in stress. Paper: [Novy-Marx 2013](http://users.nber.org/~confer/2010/APf10/Novy-Marx.pdf)""",
    },
    "🚀 Momentum": {
        "sample": "sample_mom_results.json",
        "sample1500": "sample_1500_mom_results.json",
        "blurb": "Jegadeesh-Titman (1993): buy the past 12-month winners (skipping the last month).",
        "run": run_momentum, "params": _mom_params, "frame": _mom_frame, "detail": _detail_simple,
        "how": """**Momentum** (Jegadeesh & Titman, 1993):
Rank the universe by 12-month return **skipping the most recent month**, buy the top ~100 equal-weight, rebalance monthly.
The most replicated anomaly in finance — but it crashes hard on occasion (2009), so size it knowing that.
Paper: [Jegadeesh & Titman 1993](https://smallake.kr/wp-content/uploads/2015/01/Jegadeesh_Titman_1993.pdf)""",
    },
    "⚖️ Profitable Value": {
        "sample": "sample_pv_results.json",
        "sample1500": "sample_1500_pv_results.json",
        "blurb": "Magic-Formula style: cheapest stocks among the profitable — value rank + quality rank.",
        "run": run_profitable_value, "params": _pv_params, "frame": _pv_frame, "detail": _detail_simple,
        "how": """**Profitable Value** (Greenblatt's Magic Formula idea + Fama-French 5-factor):
the universe ex-financials. **Value rank** = average rank of book/market, earnings/price, and free-cash-flow yield.
**Quality rank** = rank of gross profit ÷ assets. Buy the 30 lowest **combined rank**, equal-weight, rebalance annually.
Value alone has struggled since 2007 — pairing it with profitability fixes much of that, and the two diversify each other.
Book: Greenblatt (2005), *The Little Book That Beats the Market*; paper: [Fama-French 2015](https://tevgeniou.github.io/EquityRiskFactors/bibliography/FiveFactor.pdf)""",
    },
    "🎯 Composite": {
        "sample": "sample_composite_results.json",
        "sample1500": "sample_1500_composite_results.json",
        "blurb": "All-rounder: stocks that rank well on value, quality, momentum AND growth at once.",
        "run": run_composite, "params": _composite_params, "frame": _composite_frame, "detail": _detail_simple,
        "how": """**Composite (all-rounder)** — your intuition, formalized: a stock that is simultaneously cheap, profitable, winning, and growing is a better bet than one that only screens well on a single factor. The four factor families are also negatively correlated with each other, so the combination diversifies.
the universe ex-financials, must have positive earnings and positive free cash flow:
1. **Value rank** = average rank of book/market, earnings/price, FCF yield.
2. **Quality rank** = rank of gross profit ÷ total assets (Novy-Marx).
3. **Momentum rank** = rank of 12-month return skipping the last month (Jegadeesh-Titman).
4. **Growth rank** = rank of TTM revenue growth.
Buy the 30 lowest **combined rank** (value + quality + momentum + growth), equal-weight.
Trade-off: combining filters shrinks the candidate pool, so it can concentrate in whatever style is currently working — check the Backtest tab.""",
    },
}

# ---------- page ----------

st.set_page_config(page_title="Stock Screeners", layout="wide")
st.title("Stock Screeners")
strategy = st.segmented_control("Strategy", list(STRATEGIES.keys()), default="🌱 Undiscovered Growth")
if strategy not in STRATEGIES:
    strategy = "🌱 Undiscovered Growth"
universe_name = st.segmented_control("Universe", list(UNIVERSES.keys()), default="S&P 500",
                                     help="S&P 1500 = S&P 500 + 400 midcap + 600 smallcap — more undiscovered names, slower screens.")
if universe_name not in UNIVERSES:
    universe_name = "S&P 500"
uni = load_uni(universe_name)
cfg = STRATEGIES[strategy]
st.caption(cfg["blurb"] + f" Universe: {universe_name} ({len(uni)} stocks). Research screen, not investment advice.")

sample_key = "sample" if universe_name == "S&P 500" else "sample1500"
sample_path = os.path.join(APP_DIR, cfg[sample_key])
sample = json.load(open(sample_path)) if os.path.exists(sample_path) else None

tab_watch, tab_run, tab_backtest, tab_miss, tab_how = st.tabs(
    ["Watchlist", "Run fresh screen", "Backtest", "Near misses", "How it works"])

with tab_watch:
    if sample is None:
        st.info(f"No saved run for {strategy} on the {universe_name} yet — run a fresh screen instead.")
    else:
        st.subheader(f"Watchlist — run of {sample['run_date']} ({len(sample['watchlist'])} names)")
        st.dataframe(cfg["frame"](sample["watchlist"]), width="stretch", hide_index=True)
        st.divider()
        for w in sample["watchlist"]:
            with st.expander(f"{VERDICT_EMOJI.get(w.get('news_verdict'), '')} {w['symbol']} — {w['name']}"):
                if w.get("news_note"):
                    st.write(w["news_note"])
                st.caption(cfg["detail"](w))

with tab_run:
    st.subheader("Run a fresh screen")
    n_uni = len(uni)
    st.write(f"Pulls ~1 year of prices (Yahoo) and TTM fundamentals (SEC EDGAR) for the {universe_name} "
             f"({n_uni} stocks). Fundamentals are cached on disk, so re-runs are fast. "
             f"First run takes ~{10 if universe_name == 'S&P 500' else 30} minutes.")
    run_params = cfg["params"]()
    if st.button("Run screen", type="primary"):
        sp = json.load(open(os.path.join(APP_DIR, UNIVERSES[universe_name])))
        symbols = [u["symbol"] for u in sp]
        cik_of = {u["symbol"]: u["cik"] for u in sp}
        prog = st.progress(0.0, "Fetching prices…")
        prices, fails = fetch_prices(symbols, progress=lambda f, t: prog.progress(f * 0.25, t))
        st.caption(f"Prices: {len(prices)} ok, {len(fails)} failed")
        cache = json.load(open(CACHE_PATH)) if os.path.exists(CACHE_PATH) else {}
        funds = fetch_fundamentals(symbols, cik_of, cache,
                                   progress=lambda f, t: prog.progress(0.25 + f * 0.70, t))
        json.dump(funds, open(CACHE_PATH, "w"))
        prog.progress(0.97, "Scoring…")
        top, screened = cfg["run"](prices, funds, uni, run_params)
        prog.progress(1.0, "Done")
        st.success(f"{screened} names passed the filters — top {len(top)} shown (news verdicts: unreviewed on fresh runs).")
        df = cfg["frame"]([{"news_verdict": "UNREVIEWED", **r} for r in top])
        st.dataframe(df, width="stretch", hide_index=True)
        st.download_button("Download CSV", df.to_csv(index=False), "screen_results.csv", "text/csv")

with tab_backtest:
    st.subheader(f"Backtest — {strategy}")
    st.write("Point-in-time monthly backtest on bundled history (2017→2026): month-end prices, "
             "fundamentals as actually filed by each rebalance date. Equal weight, long only, no costs.")
    st.caption("Method notes: Sharpe uses a 0% risk-free rate. Months with no eligible holdings are "
               "scored as cash (0%). Annual strategies form each June and start earning the next month. "
               "Fundamental history is built from SEC EDGAR by an automated pipeline; known assembler "
               "artifacts and impossible values were nulled (see data_fund_v2_repair_manifest.json), "
               "but the history has not been name-by-name verified — treat results as research, not a buy list.")
    try:
        import backtest as bt
        has_data = os.path.exists(os.path.join(APP_DIR, "data_price.json")) and \
                   os.path.exists(os.path.join(APP_DIR, "data_fund_v2.json"))
    except Exception:
        has_data = False
    if not has_data:
        st.info("Backtest data files are not bundled in this copy of the app yet.")
    else:
        _, _, default_n = bt.SCREENS[strategy]
        c1, c2 = st.columns(2)
        start = c1.selectbox("Start", ["2017-01", "2020-01", "2022-01"], index=0)
        top_n = c2.number_input("Holdings (top N)", min_value=5, max_value=200, value=default_n, step=5)
        if st.button("Run backtest", type="primary"):
            with st.spinner("Running backtest…"):
                res = bt.run_backtest(strategy, uni, start_ym=start, top_n=int(top_n))
            if res.get("error"):
                st.error(res["error"])
            else:
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("CAGR (strategy)", f"{res['strat_cagr']:.1%}" if res["strat_cagr"] is not None else "n/a",
                          f"SPY {res['spy_cagr']:.1%}" if res["spy_cagr"] is not None else "")
                k2.metric("Sharpe", res["strat_sharpe"] if res["strat_sharpe"] is not None else "n/a",
                          f"SPY {res['spy_sharpe']}" if res["spy_sharpe"] is not None else "")
                k3.metric("Max drawdown", f"{res['strat_maxdd']:.1%}" if res['strat_maxdd'] is not None else "n/a",
                          f"SPY {res['spy_maxdd']:.1%}" if res["spy_maxdd"] is not None else "")
                k4.metric("Total return", f"{res['strat_total']:.1%}" if res["strat_total"] is not None else "n/a",
                          f"SPY {res['spy_total']:.1%}" if res["spy_total"] is not None else "")
                import pandas as pd
                df = pd.DataFrame({"Strategy": res["strat_curve"], "SPY": res["spy_curve"]},
                                  index=pd.to_datetime(res["months"]))
                st.line_chart(df)
                st.subheader("Yearly returns")
                ydf = pd.DataFrame(res["yearly"]).T.rename(columns={"strat": "Strategy", "spy": "SPY"})
                st.bar_chart(ydf)
                st.dataframe(ydf.style.format("{:.1%}"), width="stretch")
                st.caption(f"{res['n_months']} months, {len(res['last_holdings'])} holdings at last rebalance. "
                           f"Current {universe_name} constituents only (survivorship bias flatters results). "
                           "Monthly granularity, no transaction costs or taxes. Research, not advice.")

with tab_miss:
    st.subheader("Near misses — excluded with reason")
    if not sample or not sample.get("near_miss"):
        st.write("None recorded for this run.")
    for m in (sample.get("near_miss", []) if sample else []):
        reason = m.get("news_note") or m.get("note") or ", ".join(m.get("failed", []))
        st.write(f"**{m['symbol']}** — {reason}")

with tab_how:
    st.markdown(cfg["how"])
    st.caption("All six are research screens, not investment advice.")
