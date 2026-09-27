"""Build sp1500.json: S&P 500 (existing sp500.json) + S&P 400 + S&P 600 from Wikipedia.
CIKs from Wikipedia where present, else SEC company_tickers.json.
Output: list of {symbol, name, sector, sub, cik} with dot-style symbols (BRK.B)."""
import json, urllib.request, io, os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Muse StockMonitor research@example.com"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()

def main():
    from lxml import html as lh
    rows = []
    for url in ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
                "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"):
        doc = lh.fromstring(get(url))
        for table in doc.xpath("//table[contains(@class,'wikitable')]"):
            ths = [t.text_content().strip().lower() for t in table.xpath(".//tr[1]/th")]
            if not ths or not any("symbol" in c or "ticker" in c for c in ths):
                continue
            if not any("gics sector" in c for c in ths):
                continue
            si = next(i for i, c in enumerate(ths) if "symbol" in c or "ticker" in c)
            ni = next(i for i, c in enumerate(ths) if "securit" in c or "compan" in c)
            gi = next(i for i, c in enumerate(ths) if "gics sector" in c)
            subi = next((i for i, c in enumerate(ths) if "sub-industr" in c), None)
            ciki = next((i for i, c in enumerate(ths) if c == "cik"), None)
            for tr in table.xpath(".//tr[position()>1]"):
                tds = [t.text_content().strip() for t in tr.xpath("./td")]
                if len(tds) <= max(si, ni, gi):
                    continue
                rows.append({
                    "symbol": tds[si], "name": tds[ni], "sector": tds[gi],
                    "sub": tds[subi] if subi is not None and subi < len(tds) else "",
                    "cik": tds[ciki] if ciki is not None and ciki < len(tds) and tds[ciki] else None,
                })
            break
    # SEC ticker -> CIK map for gaps
    tick = json.loads(get("https://www.sec.gov/files/company_tickers.json"))
    tmap = {}
    for v in tick.values():
        tmap[v["ticker"].upper().replace("-", ".")] = str(v["cik_str"])
        tmap[v["ticker"].upper()] = str(v["cik_str"])
    missing = 0
    for r in rows:
        if not r["cik"]:
            r["cik"] = tmap.get(r["symbol"].upper().replace("-", "."))
            if not r["cik"]:
                missing += 1
    print("400+600 rows:", len(rows), "| CIK still missing:", missing)
    for r in [x for x in rows if not x["cik"]][:10]:
        print("  no CIK:", r["symbol"], r["name"])
    # merge with sp500 (keep its entries authoritative for the 500)
    sp500 = json.load(open(os.path.join(APP_DIR, "sp500.json")))
    have = {u["symbol"] for u in sp500}
    extra = [r for r in rows if r["symbol"] not in have and r["cik"]]
    out = sp500 + [{"symbol": r["symbol"], "name": r["name"], "sector": r["sector"],
                    "sub": r["sub"], "cik": r["cik"]} for r in extra]
    json.dump(out, open(os.path.join(APP_DIR, "sp1500.json"), "w"), indent=1)
    print("sp1500.json:", len(out), f"({len(sp500)} x SP500 + {len(extra)} new)")

if __name__ == "__main__":
    main()
