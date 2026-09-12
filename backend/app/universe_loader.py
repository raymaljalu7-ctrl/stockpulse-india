import csv, io, time
from typing import Any
import requests

CSV_URL="https://raw.githubusercontent.com/kprohith/nse-stock-analysis/master/ind_nifty500list.csv"
YAHOO_URL="https://query1.finance.yahoo.com/v7/finance/spark"
UA={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
_cache:dict[str,tuple[float,Any]]={}

def _get(url,params=None,timeout=15):
    for attempt in range(3):
        try:
            r=requests.get(url,params=params,headers=UA,timeout=timeout)
            if r.status_code==200:
                return r.json() if "json" in (r.headers.get("content-type") or "") else r.text
            if r.status_code in (429,500,502,503,504):
                time.sleep(0.8*(attempt+1))
                continue
        except Exception:
            if attempt < 2:
                time.sleep(0.5*(attempt+1))
    return None

def nifty500_symbols():
    key="symbols"; hit=_cache.get(key)
    if hit and time.time()-hit[0]<86400: return hit[1]
    text=_get(CSV_URL,timeout=20)
    if not isinstance(text,str): return []
    try:
        rows=list(csv.DictReader(io.StringIO(text)))
        out=[]
        for row in rows:
            s=str(row.get("Symbol") or "").strip().upper()
            series=str(row.get("Series") or "EQ").strip().upper()
            if s and series in {"EQ","BE"} and s not in out: out.append(s)
        _cache[key]=(time.time(),out)
        return out
    except Exception:
        return []

def yahoo_quotes(symbols):
    out=[]
    # Yahoo Spark can throttle large bursts. Smaller batches plus retries
    # avoid the previous failure mode where only the first ~50 symbols arrived.
    for i in range(0,len(symbols),20):
        batch=symbols[i:i+20]
        syms=",".join(s+".NS" for s in batch)
        params={"symbols":syms,"range":"1y","interval":"1d","indicators":"close,volume","includeTimestamps":"true","includePrePost":"false","corsDomain":"finance.yahoo.com"}
        d=_get(YAHOO_URL,params,timeout=25)
        results=((d or {}).get("spark") or {}).get("result") or [] if isinstance(d,dict) else []
        for r in results:
            responses=r.get("response") or []
            z=responses[0] if responses else r
            meta=z.get("meta") or r.get("meta") or {}
            sym=str(meta.get("symbol") or r.get("symbol") or "").replace(".NS","").upper()
            q=((z.get("indicators") or {}).get("quote") or [{}])[0]
            closes=q.get("close") or []
            vols=q.get("volume") or []
            vals=[float(x) for x in closes if isinstance(x,(int,float))]
            if not sym or not vals: continue
            price=float(meta.get("regularMarketPrice") or vals[-1])
            prev=vals[-2] if len(vals)>1 else price
            idx30=max(0,len(vals)-22)
            base30=vals[idx30] if vals[idx30] else price
            base365=vals[0] if vals[0] else price
            vol=0
            for v in reversed(vols):
                if isinstance(v,(int,float)):
                    vol=float(v); break
            out.append({
                "symbol":sym,"price":price,
                "change_pct":(price-prev)/prev*100 if prev else 0,
                "dayHigh":max(vals[-2:]) if len(vals)>=2 else price,
                "dayLow":min(vals[-2:]) if len(vals)>=2 else price,
                "yearHigh":max(vals),"yearLow":min(vals),"volume":vol,
                "perChange30d":(price-base30)/base30*100 if base30 else 0,
                "perChange365d":(price-base365)/base365*100 if base365 else 0,
                "companyName":sym,"industry":"Nifty 500 equity","ffmc":0
            })
        # Keep a small pause between Yahoo batches to avoid burst throttling.
        time.sleep(0.15)
    return out

def load_universe():
    syms=nifty500_symbols()
    if len(syms)<300: return []
    data=yahoo_quotes(syms)
    # Require a genuinely broad universe before replacing the app's fallback.
    return data if len(data)>=100 else []
