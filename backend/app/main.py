from __future__ import annotations

import io
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stockpulse")

app = FastAPI(title="StockPulse India API", version="4.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

NIFTY50 = [
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK","BAJAJ-AUTO","BAJFINANCE","BAJAJFINSV",
    "BEL","BHARTIARTL","BPCL","BRITANNIA","CIPLA","COALINDIA","DIVISLAB","DRREDDY","EICHERMOT","ETERNAL",
    "GRASIM","HCLTECH","HDFCBANK","HDFCLIFE","HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","INDUSINDBK",
    "INFY","ITC","JIOFIN","JSWSTEEL","KOTAKBANK","LT","M&M","MARUTI","NESTLEIND","NTPC","ONGC","POWERGRID",
    "RELIANCE","SBILIFE","SBIN","SHRIRAMFIN","SUNPHARMA","TATACONSUM","TATAMOTORS","TATASTEEL","TCS","TECHM",
    "TITAN","TRENT","ULTRACEMCO"
]

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}
_nse_session: requests.Session | None = None
_nse_session_at = 0.0
_cache: dict[str, tuple[float, Any]] = {}


def clean(v: Any, default=None):
    if v is None:
        return default
    try:
        if pd.isna(v) or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return default
    except Exception:
        pass
    if isinstance(v, (np.integer, np.floating)):
        return float(v)
    return v


def num(v, default=0.0):
    try:
        x = float(v)
        return default if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return default


def pct(a, b):
    a, b = num(a), num(b)
    return ((a / b) - 1) * 100 if b else 0.0


def nse_session(force=False) -> requests.Session:
    global _nse_session, _nse_session_at
    if _nse_session is not None and not force and time.time() - _nse_session_at < 600:
        return _nse_session
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        r = s.get("https://www.nseindia.com/", timeout=15)
        r.raise_for_status()
        _nse_session = s
        _nse_session_at = time.time()
        return s
    except Exception:
        _nse_session = s
        _nse_session_at = time.time()
        return s


def nse_get(path: str, params: dict[str, Any] | None = None, cache_seconds: int = 45):
    key = path + "?" + str(sorted((params or {}).items()))
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < cache_seconds:
        return cached[1]
    for attempt in range(2):
        try:
            s = nse_session(force=attempt > 0)
            r = s.get("https://www.nseindia.com" + path, params=params, timeout=20)
            if r.status_code == 200:
                data = r.json()
                _cache[key] = (time.time(), data)
                return data
            log.warning("NSE returned %s for %s", r.status_code, path)
        except Exception as exc:
            log.warning("NSE request failed %s: %s", path, exc)
        time.sleep(1.5)
    return None


def nse_history(symbol: str) -> pd.DataFrame:
    end = datetime.now().date()
    start = end - timedelta(days=800)
    params = {"symbol": symbol, "series": '"EQ"', "from": start.strftime("%d-%m-%Y"), "to": end.strftime("%d-%m-%Y")}
    data = nse_get("/api/historical/cm/equity", params=params, cache_seconds=300)
    rows = (data or {}).get("data", []) if isinstance(data, dict) else []
    if not rows:
        return pd.DataFrame()
    records = []
    for x in rows:
        records.append({
            "Date": x.get("CH_TIMESTAMP"),
            "Open": x.get("CH_OPENING_PRICE"),
            "High": x.get("CH_TRADE_HIGH_PRICE"),
            "Low": x.get("CH_TRADE_LOW_PRICE"),
            "Close": x.get("CH_CLOSING_PRICE"),
            "Prev Close": x.get("CH_PREVIOUS_CLS_PRICE"),
            "Volume": x.get("CH_TOT_TRADED_QTY"),
        })
    df = pd.DataFrame(records)
    for c in ["Open","High","Low","Close","Prev Close","Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)


def period_returns(df: pd.DataFrame, today_change: float = 0.0):
    if df.empty or "Close" not in df:
        return {"days": {"1": round(today_change,2)}, "weeks": {}, "months": {}, "years": {}}
    close = df["Close"].dropna().reset_index(drop=True)
    last = float(close.iloc[-1])
    out = {"days": {"1": round(today_change,2)}, "weeks": {}, "months": {}, "years": {}}
    for n in range(2, 31):
        idx = len(close) - n
        out["days"][str(n)] = round(pct(last, close.iloc[idx]) if idx >= 0 else 0, 2)
    for n in range(1, 13):
        idx = len(close) - (n * 5) - 1
        if idx >= 0: out["weeks"][str(n)] = round(pct(last, close.iloc[idx]), 2)
        idx = len(close) - (n * 21) - 1
        if idx >= 0: out["months"][str(n)] = round(pct(last, close.iloc[idx]), 2)
    for n in range(1, 6):
        idx = len(close) - (n * 252) - 1
        if idx >= 0: out["years"][str(n)] = round(pct(last, close.iloc[idx]), 2)
    return out


def score_history(symbol: str, df: pd.DataFrame, quote: dict | None = None):
    if df.empty or len(df) < 20:
        return None
    quote = quote or {}
    close = df["Close"].dropna()
    vol = df["Volume"].fillna(0)
    price = float(close.iloc[-1]); prev = float(close.iloc[-2]) if len(close) > 1 else price
    r20 = pct(price, close.iloc[-21]) if len(close) > 21 else pct(price, close.iloc[0])
    r60 = pct(price, close.iloc[-61]) if len(close) > 61 else r20
    r252 = pct(price, close.iloc[-253]) if len(close) > 253 else pct(price, close.iloc[0])
    high52 = float(close.tail(252).max()); low52 = float(close.tail(252).min())
    pos52 = (price-low52)/(high52-low52)*100 if high52 != low52 else 50
    v20 = float(vol.tail(20).mean()); todayv = float(vol.iloc[-1]); vchg = pct(todayv, v20) if v20 else 0
    ma20=float(close.tail(20).mean()); ma50=float(close.tail(50).mean()) if len(close)>=50 else ma20
    ma200=float(close.tail(200).mean()) if len(close)>=200 else ma50
    delta=close.diff(); gain=delta.clip(lower=0).rolling(14).mean(); loss=(-delta.clip(upper=0)).rolling(14).mean(); rs=gain/loss.replace(0,np.nan)
    rsi=float((100-(100/(1+rs))).iloc[-1]) if not rs.empty and pd.notna(rs.iloc[-1]) else 50
    technical=max(0,min(100,50+r20*1.2+r60*.45+(rsi-50)*.35+(10 if price>ma20>ma50 else -8 if price<ma50 else 0)))
    momentum=max(0,min(100,50+r20*1.3+r60*.45+vchg/20))
    volume=max(0,min(100,50+(vchg*.25 if vchg>0 else vchg*.1)))
    score=max(0,min(100,0.55*technical+0.25*momentum+0.10*volume+0.10*pos52))
    band="Strong" if score>=80 else "Potential" if score>=65 else "Watch" if score>=50 else "Avoid"
    reasons=[]
    if price>ma20>ma50: reasons.append("Price is above 20D and 50D moving averages")
    if r20>5: reasons.append(f"20D momentum is +{r20:.1f}%")
    if r60>10: reasons.append(f"60D momentum is +{r60:.1f}%")
    if vchg>25: reasons.append(f"Today's volume is {vchg:.0f}% above 20D average")
    if pos52>80: reasons.append(f"Price is in the upper {100-pos52:.0f}% of its 52-week range")
    if not reasons: reasons.append("Rank supported by measurable price, trend and volume signals")
    upside=max(-20,min(60,0.45*r20+0.25*r60+0.20*(score-50)))
    today=pct(price, prev)
    return {
        "symbol":symbol,"price":price,"change_pct":today,"final_rank_score":round(score,1),"band":band,
        "return_20d_pct":round(r20,2),"return_60d_pct":round(r60,2),"return_1y_pct":round(r252,2),"52w_position":round(pos52,1),
        "volume_today":todayv,"volume_5d_avg":float(vol.tail(5).mean()),"volume_20d_avg":v20,"volume_50d_avg":float(vol.tail(50).mean()),"volume_change_pct":round(vchg,2),
        "rsi14":round(rsi,1),"dma20":round(ma20,2),"dma50":round(ma50,2),"dma200":round(ma200,2),
        "pe":None,"pb":None,"roe":None,"roce":None,"debt_to_equity":None,"profit_margin":None,"market_cap":clean(quote.get("ffmc")),"book_value":None,"dividend_yield":None,
        "short_term_score":round((technical+momentum+volume)/3,1),"medium_term_score":round((technical+momentum+pos52)/3,1),"long_term_score":round((technical+pos52+50)/3,1),
        "estimated_upside_pct":round(upside,1),"recommendation":"BUY" if score>=75 else "WATCH" if score>=55 else "AVOID","risk":"Medium",
        "why":reasons,"period_returns":period_returns(df,today)
    }


def quote_from_index_item(x: dict):
    return {
        "symbol":x.get("symbol"), "price":num(x.get("lastPrice")), "change_pct":num(x.get("pChange")),
        "dayHigh":num(x.get("dayHigh")), "dayLow":num(x.get("dayLow")), "yearHigh":num(x.get("yearHigh")), "yearLow":num(x.get("yearLow")),
        "volume":num(x.get("totalTradedVolume")), "perChange30d":num(x.get("perChange30d")), "perChange365d":num(x.get("perChange365d")),
        "companyName":(x.get("meta") or {}).get("companyName") or x.get("symbol"), "industry":(x.get("meta") or {}).get("industry"), "ffmc":num(x.get("ffmc"))
    }


def current_universe():
    data=nse_get("/api/equity-stockIndices", {"index":"NIFTY 50"}, cache_seconds=30)
    rows=(data or {}).get("data",[]) if isinstance(data,dict) else []
    return [quote_from_index_item(x) for x in rows if x.get("symbol") in NIFTY50]


def build_snapshot(q: dict):
    price=q["price"]; low=q["yearLow"]; high=q["yearHigh"]
    pos=(price-low)/(high-low)*100 if high>low else 50
    r30=q["perChange30d"]; r365=q["perChange365d"]
    momentum=max(0,min(100,50+r30*1.5+r365*.12+q["change_pct"]*2))
    technical=max(0,min(100,50+r30*1.3+r365*.08+(pos-50)*.25))
    volume=50
    score=max(0,min(100,.55*technical+.30*momentum+.15*pos))
    band="Strong" if score>=80 else "Potential" if score>=65 else "Watch" if score>=50 else "Avoid"
    reasons=[]
    if q["change_pct"]>1: reasons.append(f"Today's price change is +{q['change_pct']:.2f}%")
    if r30>5: reasons.append(f"30D momentum is +{r30:.1f}%")
    if r365>10: reasons.append(f"1Y momentum is +{r365:.1f}%")
    if pos>80: reasons.append("Price is close to the upper end of its 52-week range")
    if q["volume"]>0: reasons.append("Live NSE volume is available")
    if not reasons: reasons.append("Rank supported by live NSE price, momentum and 52-week position")
    upside=max(-20,min(60,.5*r30+.15*r365+.2*(score-50)))
    return {
        "symbol":q["symbol"],"price":price,"change_pct":q["change_pct"],"final_rank_score":round(score,1),"band":band,
        "return_20d_pct":round(r30,2),"return_60d_pct":round(r30,2),"return_1y_pct":round(r365,2),"52w_position":round(pos,1),
        "volume_today":q["volume"],"volume_5d_avg":0,"volume_20d_avg":0,"volume_50d_avg":0,"volume_change_pct":0,
        "rsi14":50,"dma20":0,"dma50":0,"dma200":0,"pe":None,"pb":None,"roe":None,"roce":None,"debt_to_equity":None,"profit_margin":None,"market_cap":q["ffmc"],"book_value":None,"dividend_yield":None,
        "short_term_score":round(momentum,1),"medium_term_score":round((momentum+technical)/2,1),"long_term_score":round((technical+pos+50)/3,1),
        "estimated_upside_pct":round(upside,1),"recommendation":"BUY" if score>=75 else "WATCH" if score>=55 else "AVOID","risk":"Medium",
        "why":reasons,"period_returns":{"days":{"1":round(q["change_pct"],2)},"weeks":{"1":round(r30/4.3,2)},"months":{"1":round(r30,2)},"years":{"1":round(r365,2)}}
    }


@app.get("/health")
def health():
    return {"status":"ok","service":"stockpulse-india-api","version":"4.2","data_source":"NSE"}


@app.get("/api/screener/top")
def top(limit:int=50,min_quality:float=0):
    universe=current_universe()
    if not universe:
        raise HTTPException(503,"NSE live market data is temporarily unavailable. Please retry shortly.")
    items=[build_snapshot(q) for q in universe]
    items=[x for x in items if x["final_rank_score"]>=min_quality]
    items.sort(key=lambda x:x["final_rank_score"],reverse=True)
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"items":items[:max(1,min(limit,50))],"universe_size":len(universe)}


@app.get("/api/stock/{symbol}")
def stock(symbol:str):
    s=symbol.upper().replace(".NS","")
    universe=current_universe()
    q=next((x for x in universe if x["symbol"]==s),None)
    df=nse_history(s)
    if df.empty:
        if q: return build_snapshot(q) | {"company_name":q["companyName"],"sector":q["industry"],"industry":q["industry"],"business_summary":None,"pros":build_snapshot(q)["why"],"cons":["Detailed historical feed is temporarily unavailable"]}
        raise HTTPException(503,"Live NSE market data unavailable for this stock")
    x=score_history(s,df,q or {})
    if not x: raise HTTPException(503,"Insufficient historical market data")
    out=dict(x)
    out["company_name"]=(q or {}).get("companyName") or s
    out["sector"]=(q or {}).get("industry"); out["industry"]=(q or {}).get("industry"); out["business_summary"]=None
    out["52w_high"]=(q or {}).get("yearHigh") or float(df["Close"].tail(252).max())
    out["52w_low"]=(q or {}).get("yearLow") or float(df["Close"].tail(252).min())
    out["face_value"]=None; out["employees"]=None; out["target_mean"]=None; out["analyst_count"]=None
    out["pros"]=x["why"][:5]
    out["cons"]=[]
    if x["rsi14"]>70: out["cons"].append("RSI indicates an overbought short-term setup")
    if x["price"]<x["dma50"]: out["cons"].append("Price is below the 50D moving average")
    if not out["cons"]: out["cons"].append("No major quantitative trend risk flag was detected")
    return out


@app.get("/api/market")
def market():
    data=nse_get("/api/allIndices",cache_seconds=30)
    rows=(data or {}).get("data",[]) if isinstance(data,dict) else []
    wanted={"NIFTY 50","NIFTY BANK"}
    result=[]
    for x in rows:
        if x.get("index") in wanted or x.get("indexSymbol") in {"NIFTY","NIFTY BANK"}:
            result.append({"symbol":x.get("index") or x.get("indexSymbol"),"price":num(x.get("last")),"change_pct":num(x.get("percentChange"))})
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"indices":result}


@app.get("/api/fno/{symbol}")
def fno(symbol:str):
    return {"status":"unavailable","items":[],"message":"Live derivative feed is not enabled in this personal-use build."}
