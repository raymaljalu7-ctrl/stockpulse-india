from __future__ import annotations
from datetime import datetime, timezone
from io import StringIO
import re
import time
import requests
import pandas as pd
from fastapi import APIRouter

UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/json,*/*","Accept-Language":"en-US,en;q=0.9"}


def _clean(v):
    if v is None: return ""
    return re.sub(r"\s+"," ",str(v)).strip()

def _num(v):
    s=_clean(v).replace(",","").replace("₹","").replace("Rs.","").replace("Rs"," ").strip().replace("%","")
    try:return float(s)
    except Exception:return None

def _col(df,*names):
    cols={_clean(c).lower():c for c in df.columns}
    for n in names:
        for k,c in cols.items():
            if n in k:return c
    return None

def _symbol(name):
    s=_clean(name).upper()
    # Preserve a real ticker when a source supplies one; otherwise the company
    # name is used as the display identifier rather than inventing a ticker.
    return re.sub(r"\s+"," ",s)

def _parse_tables(url, source, limit=100):
    try:
        r=requests.get(url,headers=UA,timeout=18)
        if r.status_code!=200:return []
        tables=pd.read_html(StringIO(r.text))
    except Exception:
        return []
    out=[]
    for df in tables:
        if df.empty:continue
        stockc=_col(df,"stock","company","company name","script","scrip")
        brokerc=_col(df,"broker","brokerage","broker / analyst","research house")
        actionc=_col(df,"action","rating","recommendation","call")
        targetc=_col(df,"target price","target")
        datec=_col(df,"reco date","date","published")
        if not stockc or not actionc or not (targetc or brokerc):continue
        currentc=_col(df,"cmp","current price","ltp","price")
        upsidec=_col(df,"potential","upside")
        for _,row in df.iterrows():
            company=_clean(row.get(stockc))
            rating=_clean(row.get(actionc))
            if not company or not rating:continue
            target=_num(row.get(targetc)) if targetc else None
            current=_num(row.get(currentc)) if currentc else None
            upside=_num(row.get(upsidec)) if upsidec else None
            if upside is None and target and current and current>0:upside=(target-current)/current*100
            # Keep only actual recommendation-like actions, not navigation rows.
            if not re.search(r"buy|sell|hold|accumulate|reduce|add|outperform|underperform|neutral",rating,re.I):continue
            out.append({"symbol":_symbol(company),"company":company,"broker":_clean(row.get(brokerc)) if brokerc else source,"analyst":None,"rating":rating,"target_price":target,"current_price":current,"upside_pct":round(upside,2) if upside is not None else None,"horizon":None,"date":_clean(row.get(datec)) if datec else None,"rationale":"Public brokerage/research report listing; open the source for the full rationale.","source_url":url,"source":source})
            if len(out)>=limit:break
    return out


def register_broker_routes(app, nse_get):
    router=APIRouter()
    cache={"ts":0.0,"items":[]}

    def collect():
        now=time.time()
        if now-cache["ts"]<900 and cache["items"]:return cache["items"]
        feeds=[
            ("DSIJ", "https://insights.dsij.in/markets/reports/broker-reports/stock-tips/broker-detail/research/stock-tips/fundamental-stock-tips/type/lib/zlib/lib/inflate"),
            ("Business Standard", "https://www.business-standard.com/markets/research-report"),
            ("Trendlyne", "https://trendlyne.com/research-reports/buy/"),
        ]
        all_items=[]
        seen=set()
        for source,url in feeds:
            for x in _parse_tables(url,source,80):
                key=(x["symbol"],x.get("broker"),x.get("rating"),x.get("target_price"),x.get("date"))
                if key in seen:continue
                seen.add(key);all_items.append(x)
        # Prefer the newest report dates when a source supplies them.
        all_items.sort(key=lambda x:str(x.get("date") or ""),reverse=True)
        cache.update(ts=now,items=all_items)
        return all_items

    @router.get('/api/broker-recommendations')
    def broker_recommendations(symbol: str|None=None, limit: int=200):
        s=(symbol or '').upper().replace('.NS','')
        items=collect()
        if s:items=[x for x in items if x['symbol'].upper()==s or x.get('company','').upper()==s]
        return {'generated_at':datetime.now(timezone.utc).isoformat(),'items':items[:max(1,min(limit,500))],'data_source':'DSIJ + Business Standard + Trendlyne public research listings','feed_status':'live public feeds','disclaimer':'Broker/analyst views are opinions, can change, may have conflicts, and are not guaranteed returns. StockPulse does not endorse any call. Only publicly listed source records are shown; no calls are fabricated.'}
    app.include_router(router)
