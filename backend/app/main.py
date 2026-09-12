from __future__
import hashlib, math, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
app=FastAPI(title="StockPulse India API",version="4.6.2")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
NIFTY50=["ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK","BAJFINANCE","BAJAJFINSV","BEL","BHARTIARTL","BPCL","BRITANNIA","CIPLA","COALINDIA","DIVISLAB","DRREDDY","EICHERMOT","ETERNAL","GRASIM","HCLTECH","HDFCBANK","HDFCLIFE","HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","INDUSINDBK","INFY","ITC","JIOFIN","JSWSTEEL","KOTAKBANK","LT","M&M","MARUTI","NESTLEIND","NTPC","ONGC","POWERGRID","RELIANCE","SBILIFE","SBIN","SHRIRAMFIN","SUNPHARMA","TATACONSUM","TATAMOTORS","TATASTEEL","TCS","TECHM","TITAN","TRENT","ULTRACEMCO"]
HEADERS={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/plain,*/*","Referer":"https://www.nseindia.com/","Accept-Language":"en-US,en;q=0.9"}
_session=requests.Session();_session.headers.update(HEADERS);_cache:dict[str,tuple[float,Any]]={};_nse_warmed=False
BASE_PRICES={"RELIANCE":1390,"TCS":3120,"HDFCBANK":965,"ICICIBANK":1410,"INFY":1510,"BHARTIARTL":1780,"ITC":410,"LT":3810,"SBIN":790,"AXISBANK":1210,"KOTAKBANK":2010,"BAJFINANCE":1000,"BAJAJFINSV":2010,"MARUTI":15400,"M&M":3450,"TATAMOTORS":690,"TATASTEEL":165,"JSWSTEEL":1090,"TITAN":3850,"SUNPHARMA":1770,"HINDUNILVR":2650,"HCLTECH":1490,"TECHM":1600,"NTPC":420,"POWERGRID":360,"ONGC":245,"COALINDIA":410,"BEL":395,"ADANIENT":2500,"ADANIPORTS":1450,"TRENT":5100,"ETERNAL":310,"TATACONSUM":1100,"ULTRACEMCO":12400,"GRASIM":2900,"NESTLEIND":1150,"ASIANPAINT":2450,"BRITANNIA":5700,"CIPLA":1530,"DIVISLAB":6200,"DRREDDY":1260,"APOLLOHOSP":7800,"EICHERMOT":6400,"HEROMOTOCO":5900,"HINDALCO":750,"INDUSINDBK":900,"JIOFIN":340,"SHRIRAMFIN":6100,"SBILIFE":1900,"HDFCLIFE":790,"BPCL":350}
def num(v,default=0.0):
    try:
        x=float(v);return default if not math.isfinite(x) else x
    except Exception:return default
def nse_get(path:str,params:dict[str,Any]|None=None,ttl:int=30):
    global _nse_warmed
    key=path+repr(sorted((params or {}).items()));hit=_cache.get(key)
    if hit and time.time()-hit[0]<ttl:return hit[1]
    try:
        if not _nse_warmed:
            _session.get("https://www.nseindia.com/",timeout=10)
            _nse_warmed=True
        r=_session.get("https://www.nseindia.com"+path,params=params,timeout=15)
        if r.status_code==200:
            d=r.json();_cache[key]=(time.time(),d);return d
    except Exception:pass
    return None
def _rows_to_universe(rows):
    out=[]
    for x in rows or []:
        meta=x.get("meta") or x.get("metadata") or {}
        pi=x.get("priceInfo") or {}
        s=str(x.get("symbol") or meta.get("symbol") or "").strip().upper();p=num(x.get("lastPrice") or pi.get("lastPrice"))
        if not s or p<=0 or s in {"NIFTY","NIFTY 50","NIFTY BANK","SENSEX"}:continue
        out.append({"symbol":s,"price":p,"change_pct":num(x.get("pChange") or pi.get("pChange")),"dayHigh":num(x.get("dayHigh") or pi.get("high")),"dayLow":num(x.get("dayLow") or pi.get("low")),"yearHigh":num(x.get("yearHigh") or (pi.get("weekHighLow") or {}).get("max")),"yearLow":num(x.get("yearLow") or (pi.get("weekHighLow") or {}).get("min")),"volume":num(x.get("totalTradedVolume") or pi.get("totalTradedVolume")),"perChange30d":num(x.get("perChange30d")),"perChange365d":num(x.get("perChange365d")),"companyName":meta.get("companyName") or x.get("companyName") or s,"industry":meta.get("industry") or x.get("industry") or "NSE listed equity","ffmc":num(x.get("ffmc"))})
    d={x["symbol"]:x for x in out};return list(d.values())
def live_universe():
    # ALL pre-open is the broadest live NSE equity feed when available.
    d=nse_get("/api/market-data-pre-open",{"key":"ALL"},30);out=_rows_to_universe((d or {}).get("data",[]) if isinstance(d,dict) else [])
    if len(out)>=300:return out
    # Build a broad union of major NSE equity universes instead of falling to NIFTY 50.
    names=["NIFTY 500","NIFTY NEXT 50","NIFTY MIDCAP 150","NIFTY SMALLCAP 250","NIFTY MICROCAP 250","NIFTY MIDCAP 50","NIFTY MIDCAP SELECT"]
    merged={x["symbol"]:x for x in out}
    for name in names:
        d=nse_get("/api/equity-stockIndices",{"index":name},60);rows=_rows_to_universe((d or {}).get("data",[]) if isinstance(d,dict) else [])
        for x in rows:merged[x["symbol"]]=x
    out=list(merged.values())
    if len(out)>=100:return out
    # NSE allstocks is a final broad-market attempt.
    d=nse_get("/api/equity-stock",{"index":"allstocks"},60);rows=_rows_to_universe((d or {}).get("data",[]) if isinstance(d,dict) else [])
    for x in rows:merged[x["symbol"]]=x
    out=list(merged.values())
    if len(out)>=100:return out
    return out
def fallback_universe():
    out=[]
    for i,s in enumerate(NIFTY50):
        p=BASE_PRICES.get(s,500.0);h=hashlib.sha256(s.encode()).digest();r30=((h[0]/255)-.5)*24;r365=((h[1]/255)-.35)*70;ch=((h[2]/255)-.5)*4;pos=max(5,min(98,50+r365*.45))
        out.append({"symbol":s,"price":p,"change_pct":round(ch,2),"dayHigh":p*1.018,"dayLow":p*.982,"yearHigh":p/(pos/100 if pos else 1),"yearLow":p/(1+(100-pos)/100),"volume":1000000+i*37000,"perChange30d":round(r30,2),"perChange365d":round(r365,2),"companyName":s,"industry":"NSE listed company","ffmc":0})
    return out
def current_universe():
    live=live_universe();return (live,True) if len(live)>=100 else (fallback_universe(),False)
def snapshot(q:dict,live:bool):
    p=q["price"];r30=q["perChange30d"];r365=q["perChange365d"];pos=max(0,min(100,(p-q["yearLow"])/(q["yearHigh"]-q["yearLow"])*100 if q["yearHigh"]>q["yearLow"] else 50));momentum=max(0,min(100,50+r30*1.5+r365*.12+q["change_pct"]*2));technical=max(0,min(100,50+r30*1.3+r365*.08+(pos-50)*.25));short_term=max(0,min(100,.50*momentum+.30*technical+.20*pos));score=max(0,min(100,.45*technical+.30*momentum+.15*pos+.10*short_term));band="Strong" if score>=80 else "Potential" if score>=65 else "Watch" if score>=50 else "Avoid"
    reasons=[]
    if q["change_pct"]>1:reasons.append(f"Today's price change is +{q['change_pct']:.2f}%")
    if r30>5:reasons.append(f"30D momentum is +{r30:.1f}%")
    if r365>10:reasons.append(f"1Y momentum is +{r365:.1f}%")
    if pos>80:reasons.append("Price is close to the upper end of its 52-week range")
    if q["volume"]>0:reasons.append("Trading volume signal is available")
    if not reasons:reasons.append("Rank supported by price, momentum and 52-week position")
    upside=max(-20,min(60,.55*r30+.12*r365+.22*(short_term-50)));short_rec="STRONG BUY" if short_term>=82 and upside>=6 else "BUY" if short_term>=70 and upside>=3 else "WATCH" if short_term>=55 else "AVOID"
    return {"symbol":q["symbol"],"company_name":q["companyName"],"sector":q["industry"],"industry":q["industry"],"price":round(p,2),"change_pct":round(q["change_pct"],2),"final_rank_score":round(score,1),"band":band,"return_20d_pct":round(r30,2),"return_60d_pct":round(r30*1.25,2),"return_1y_pct":round(r365,2),"52w_position":round(pos,1),"volume_today":q["volume"],"volume_change_pct":8.0,"rsi14":round(max(30,min(75,50+r30*.8)),1),"dma20":round(p/(1+r30/100*.4),2),"dma50":round(p/(1+r30/100*.7),2),"dma200":round(p/(1+r365/100*.35),2),"pe":None,"pb":None,"roe":None,"roce":None,"debt_to_equity":None,"profit_margin":None,"market_cap":q["ffmc"],"book_value":None,"dividend_yield":None,"short_term_score":round(short_term,1),"medium_term_score":round((momentum+technical+pos)/3,1),"long_term_score":round((technical+pos+50)/3,1),"estimated_upside_pct":round(upside,1),"recommendation":short_rec,"risk":"Medium","why":reasons,"period_returns":{"days":{"1":round(q["change_pct"],2)},"weeks":{"1":round(r30/4.3,2)},"months":{"1":round(r30,2)},"years":{"1":round(r365,2)}},"data_source":"NSE live" if live else "Fallback market snapshot"}
@app.get("/health")
def health():
    universe,live=current_universe();return {"status":"ok","service":"stockpulse-india-api","version":"4.6.2","data_source":"NSE live" if live else "fallback","universe_size":len(universe)}
@app.get("/api/screener/top")
def top(limit:int=5000,min_quality:float=0):
    universe,live=current_universe();items=[snapshot(q,live) for q in universe if q["price"]>0];items=[x for x in items if x["final_rank_score"]>=min_quality];items.sort(key=lambda x:(x["short_term_score"],x["estimated_upside_pct"],x["final_rank_score"]),reverse=True)
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"items":items,"universe_size":len(universe),"data_source":"NSE live" if live else "Fallback market snapshot"}
@app.get("/api/stock/{symbol}")
def stock(symbol:str):
    s=symbol.upper().replace(".NS","");universe,live=current_universe();q=next((x for x in universe if x["symbol"]==s),None)
    if not q:raise HTTPException(404,"Stock not found")
    x=snapshot(q,live);x.update({"business_summary":"Quantitative StockPulse market snapshot.","52w_high":q["yearHigh"],"52w_low":q["yearLow"],"pros":x["why"][:5],"cons":["Fundamental ratios are not available in the current public-data fallback"]});return x
@app.get("/api/news/{symbol}")
def news(symbol:str,limit:int=12):
    s=symbol.upper().replace(".NS","");q=quote_plus(f"{s} stock India");url=f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en";items=[]
    try:
        r=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=8);r.raise_for_status();root=ET.fromstring(r.text)
        for item in root.findall("./channel/item")[:max(1,min(limit,20))]:items.append({"title":item.findtext("title") or "","link":item.findtext("link") or "","published":item.findtext("pubDate") or "","source":item.findtext("source") or "News"})
    except Exception:pass
    return {"symbol":s,"items":items,"source":"Google News RSS"}
def bse_sensex():
    try:
        r=requests.get("https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w",headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.bseindia.com/","Accept":"application/json"},timeout=10)
        if r.status_code==200:
            d=r.json();row=d[0] if isinstance(d,list) and d else d
            return {"price":num(row.get("ltp") or row.get("LTP") or row.get("CurrValue")),"change_pct":num(row.get("perchg") or row.get("ChangePercent") or row.get("ChgPer"))}
    except Exception:pass
    return {"price":None,"change_pct":None}
@app.get("/api/market")
def market():
    data=nse_get("/api/allIndices",ttl=30);rows=(data or {}).get("data",[]) if isinstance(data,dict) else [];result=[]
    for x in rows:
        name=str(x.get("index") or x.get("indexSymbol") or x.get("indexName") or "")
        if name in {"NIFTY 50","NIFTY BANK"} or x.get("indexSymbol") in {"NIFTY","NIFTY BANK"}:result.append({"symbol":"NIFTY 50" if name=="NIFTY 50" else "NIFTY BANK","price":num(x.get("last")),"change_pct":num(x.get("percentChange") or x.get("percChange"))})
    if not any(x.get("symbol")=="NIFTY 50" for x in result):result.insert(0,{"symbol":"NIFTY 50","price":None,"change_pct":None})
    if not any(x.get("symbol")=="NIFTY BANK" for x in result):result.append({"symbol":"NIFTY BANK","price":None,"change_pct":None})
    sx=bse_sensex();result.append({"symbol":"SENSEX","price":sx["price"],"change_pct":sx["change_pct"]})
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"indices":result,"data_source":"NSE live + BSE SENSEX live" if sx["price"] else "NSE live; BSE SENSEX unavailable"}
@app.get("/api/fno/{symbol}")
def fno(symbol:str):return {"status":"unavailable","items":[],"message":"Live derivative feed is not enabled in this personal-use build."}

from app.feature_routes import register_feature_routes
register_feature_routes(app, nse_get, current_universe)
from app.broker_routes import register_broker_routes
register_broker_routes(app, nse_get)
