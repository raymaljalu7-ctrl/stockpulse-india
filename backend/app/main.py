from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="StockPulse India API", version="4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

NIFTY50 = [
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK","BAJAJ-AUTO","BAJFINANCE","BAJAJFINSV",
    "BEL","BHARTIARTL","BPCL","BRITANNIA","CIPLA","COALINDIA","DIVISLAB","DRREDDY","EICHERMOT","ETERNAL",
    "GRASIM","HCLTECH","HDFCBANK","HDFCLIFE","HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","INDUSINDBK",
    "INFY","ITC","JIOFIN","JSWSTEEL","KOTAKBANK","LT","M&M","MARUTI","NESTLEIND","NTPC","ONGC","POWERGRID",
    "RELIANCE","SBILIFE","SBIN","SHRIRAMFIN","SUNPHARMA","TATACONSUM","TATAMOTORS","TATASTEEL","TCS","TECHM",
    "TITAN","TRENT","ULTRACEMCO"
]


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


def pct(a, b):
    return ((a / b) - 1) * 100 if b not in (None, 0) and a is not None else 0.0


def history(symbol: str, period="1y"):
    return yf.Ticker(symbol + ".NS").history(period=period, auto_adjust=False)


def period_returns(df: pd.DataFrame):
    if df.empty:
        return {"days": {}, "weeks": {}, "months": {}, "years": {}}
    close = df["Close"].dropna()
    last = float(close.iloc[-1])
    out = {"days": {}, "weeks": {}, "months": {}, "years": {}}
    for n in range(1, 31):
        out["days"][str(n)] = round(pct(last, float(close.iloc[-n-1])) if len(close) > n else 0, 2)
    for n in range(1, 13):
        idx = -(n * 5 + 1)
        out["weeks"][str(n)] = round(pct(last, float(close.iloc[idx])) if len(close) > abs(idx) else 0, 2)
        idxm = -(n * 21 + 1)
        out["months"][str(n)] = round(pct(last, float(close.iloc[idxm])) if len(close) > abs(idxm) else 0, 2)
    for n in range(1, 6):
        idx = -(n * 252 + 1)
        out["years"][str(n)] = round(pct(last, float(close.iloc[idx])) if len(close) > abs(idx) else 0, 2)
    return out


def score_stock(symbol: str):
    t = yf.Ticker(symbol + ".NS")
    df = t.history(period="2y", auto_adjust=False)
    if df.empty:
        return None
    close = df["Close"].dropna(); vol = df["Volume"].fillna(0)
    price = float(close.iloc[-1]); prev = float(close.iloc[-2]) if len(close) > 1 else price
    r20 = pct(price, float(close.iloc[-21])) if len(close) > 21 else 0
    r60 = pct(price, float(close.iloc[-61])) if len(close) > 61 else 0
    r252 = pct(price, float(close.iloc[-253])) if len(close) > 253 else 0
    high52 = float(close.tail(252).max()); low52 = float(close.tail(252).min())
    pos52 = (price-low52)/(high52-low52)*100 if high52 != low52 else 50
    v20 = float(vol.tail(20).mean()); v5 = float(vol.tail(5).mean()); todayv = float(vol.iloc[-1])
    vchg = pct(todayv, v20) if v20 else 0
    ma20=float(close.tail(20).mean()); ma50=float(close.tail(50).mean()); ma200=float(close.tail(200).mean()) if len(close)>=200 else ma50
    delta=close.diff(); gain=delta.clip(lower=0).rolling(14).mean(); loss=(-delta.clip(upper=0)).rolling(14).mean(); rs=gain/loss.replace(0,np.nan); rsi=float((100-(100/(1+rs))).iloc[-1]) if not rs.empty else 50
    info={}
    try: info=t.info or {}
    except Exception: info={}
    pe=clean(info.get("trailingPE")); pb=clean(info.get("priceToBook")); roe=clean(info.get("returnOnEquity")); roce=None
    debt=clean(info.get("debtToEquity")); margin=clean(info.get("profitMargins")); mcap=clean(info.get("marketCap")); book=clean(info.get("bookValue")); divy=clean(info.get("dividendYield"))
    fund=50
    if roe is not None: fund += max(-15,min(20,(roe*100-12)*1.0))
    if debt is not None: fund += max(-15,min(10,(80-debt)/8))
    if margin is not None: fund += max(-10,min(10,(margin*100-8)*0.8))
    val=50
    if pe is not None: val += max(-15,min(15,(30-pe)*0.7))
    if pb is not None: val += max(-10,min(10,(5-pb)*1.5))
    technical=max(0,min(100,50 + r20*1.2 + r60*.45 + (rsi-50)*.45 + (10 if price>ma20>ma50 else -8 if price<ma50 else 0)))
    momentum=max(0,min(100,50+r20*1.3+r60*.45+(vchg/20)))
    volume=max(0,min(100,50+(vchg*.25 if vchg>0 else vchg*.1)))
    catalyst=55 if r20>0 and vchg>20 else 45
    risk=50
    if debt is not None and debt>150:risk-=20
    if pe is not None and pe>60:risk-=15
    score=0.35*fund+0.20*val+0.20*((technical+momentum)/2)+0.15*catalyst+0.10*risk
    score=max(0,min(100,score))
    band="Strong" if score>=80 else "Potential" if score>=65 else "Watch" if score>=50 else "Avoid"
    reasons=[]
    if price>ma20>ma50: reasons.append("Price is above 20D and 50D moving averages")
    if r20>5: reasons.append(f"20D momentum is +{r20:.1f}%")
    if r60>10: reasons.append(f"60D momentum is +{r60:.1f}%")
    if vchg>25: reasons.append(f"Today's volume is {vchg:.0f}% above 20D average")
    if roe is not None and roe>0.15: reasons.append(f"ROE is {roe*100:.1f}%")
    if debt is not None and debt<80: reasons.append(f"Debt/equity is {debt:.0f}%")
    if pe is not None and pe<30: reasons.append(f"PE is {pe:.1f}, below the model's 30x valuation reference")
    if not reasons: reasons.append("Rank supported primarily by measurable price and trend signals")
    upside=max(-20,min(60,0.45*r20+0.25*r60+0.20*(score-50)))
    return {
        "symbol":symbol,"price":price,"change_pct":pct(price,prev),"final_rank_score":round(score,1),"band":band,
        "return_20d_pct":round(r20,2),"return_60d_pct":round(r60,2),"return_1y_pct":round(r252,2),"52w_position":round(pos52,1),
        "volume_today":todayv,"volume_5d_avg":v5,"volume_20d_avg":v20,"volume_50d_avg":float(vol.tail(50).mean()),"volume_change_pct":round(vchg,2),
        "rsi14":round(rsi,1),"dma20":round(ma20,2),"dma50":round(ma50,2),"dma200":round(ma200,2),
        "pe":pe,"pb":pb,"roe":roe,"roce":roce,"debt_to_equity":debt,"profit_margin":margin,"market_cap":mcap,"book_value":book,"dividend_yield":divy,
        "short_term_score":round((technical+momentum+volume)/3,1),"medium_term_score":round((technical+momentum+fund)/3,1),"long_term_score":round((fund+val+technical)/3,1),
        "estimated_upside_pct":round(upside,1),"recommendation":"BUY" if score>=75 else "WATCH" if score>=55 else "AVOID","risk":"High" if risk<40 else "Medium" if risk<65 else "Lower",
        "why":reasons,"period_returns":period_returns(df)
    }


@app.get("/health")
def health(): return {"status":"ok","service":"stockpulse-india-api","version":"4.0"}

@app.get("/api/screener/top")
def top(limit:int=50,min_quality:float=0):
    items=[]
    for s in NIFTY50:
        try:
            x=score_stock(s)
            if x and x["final_rank_score"]>=min_quality: items.append(x)
        except Exception:
            continue
    items.sort(key=lambda x:x["final_rank_score"],reverse=True)
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"items":items[:max(1,min(limit,50))]}

@app.get("/api/stock/{symbol}")
def stock(symbol:str):
    s=symbol.upper().replace(".NS","")
    try:
        x=score_stock(s)
        if not x: raise HTTPException(404,"No market data")
        t=yf.Ticker(s+".NS")
        try: info=t.info or {}
        except Exception: info={}
        out=dict(x)
        out["company_name"]=info.get("longName") or s
        out["sector"]=info.get("sector"); out["industry"]=info.get("industry"); out["business_summary"]=info.get("longBusinessSummary")
        out["52w_high"]=clean(info.get("fiftyTwoWeekHigh")); out["52w_low"]=clean(info.get("fiftyTwoWeekLow")); out["face_value"]=clean(info.get("faceValue"))
        out["employees"]=clean(info.get("fullTimeEmployees")); out["target_mean"]=clean(info.get("targetMeanPrice")); out["analyst_count"]=clean(info.get("numberOfAnalystOpinions"))
        out["pros"]=[r for r in x["why"] if "Debt" in r or "ROE" in r or "momentum" in r][:5]
        out["cons"]=[]
        if x["pe"] and x["pe"]>45: out["cons"].append("Valuation is elevated versus the model reference")
        if x["debt_to_equity"] and x["debt_to_equity"]>120: out["cons"].append("Debt/equity is elevated")
        if x["rsi14"]>70: out["cons"].append("RSI indicates an overbought short-term setup")
        if not out["cons"]: out["cons"].append("No major quantitative risk flag was detected by the current model")
        return out
    except HTTPException: raise
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/market")
def market():
    result=[]
    for s in ["^NSEI","^NSEBANK"]:
        try:
            df=yf.Ticker(s).history(period="5d",auto_adjust=False)
            if not df.empty:
                result.append({"symbol":s,"price":float(df.Close.iloc[-1]),"change_pct":pct(float(df.Close.iloc[-1]),float(df.Close.iloc[-2])) if len(df)>1 else 0})
        except Exception: pass
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"indices":result}

@app.get("/api/fno/{symbol}")
def fno(symbol:str): return {"status":"unavailable","items":[],"message":"Live derivative feed is not enabled in this personal-use build."}
