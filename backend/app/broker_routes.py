from __future__ import annotations
from datetime import datetime, timezone
import html as html_lib
import re
import time
import xml.etree.ElementTree as ET
import requests
import pandas as pd
from io import StringIO
from fastapi import APIRouter

UA={
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
    "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language":"en-US,en;q=0.9",
    "Referer":"https://www.moneycontrol.com/",
    "Connection":"keep-alive",
}

ACTION_RE=r"Buy|Sell|Hold|Accumulate|Reduce|Add|Outperform|Underperform|Neutral|Overweight|Equalweight"


def _clean(v):
    if v is None:return ""
    return re.sub(r"\s+"," ",html_lib.unescape(str(v))).strip()


def _num(v):
    s=_clean(v).replace(",","").replace("₹","").replace("Rs.","").replace("Rs","").replace("%","").strip()
    try:return float(s)
    except Exception:return None


def _symbol(name):
    return re.sub(r"\s+"," ",_clean(name).upper())


def _item(company,broker,rating,target,date=None,source="Moneycontrol",url=None):
    return {
        "symbol":_symbol(company),"company":company,"broker":broker or source,"analyst":None,
        "rating":rating.upper(),"target_price":target,"current_price":None,"upside_pct":None,
        "horizon":None,"date":date,"rationale":"Public brokerage/research listing; open the source for the full report.",
        "source_url":url or "https://www.moneycontrol.com/news/broker-research-reports-13search-reports-13.html/",
        "source":source,
    }


def _parse_reco_text(text,source="Moneycontrol",url=None,limit=100):
    text=_clean(text)
    # Handles both the listing headline and the explanatory sentence used by Moneycontrol.
    pat=re.compile(
        rf"(?P<action>{ACTION_RE})\s+(?P<company>[^;\n]{{2,100}});\s*target of Rs\.?\s*(?P<target>[0-9,]+(?:\.\d+)?)\s*:\s*(?P<broker>[^;\n]{{2,100}}?)(?=\s+(?:is|has|recommended)|\s*$)",re.I)
    out=[];seen=set()
    for m in pat.finditer(text):
        company=_clean(m.group("company"));broker=_clean(m.group("broker"));rating=_clean(m.group("action"));target=_num(m.group("target"))
        key=(company.upper(),broker.upper(),rating.upper(),target)
        if not company or key in seen:continue
        seen.add(key)
        tail=text[m.end():m.end()+700]
        dm=re.search(r"research report dated\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",tail,re.I)
        date=dm.group(1) if dm else None
        out.append(_item(company,broker,rating,target,date,source,url))
        if len(out)>=limit:break
    return out


def _parse_html(url,source="Moneycontrol",limit=100):
    try:
        r=requests.get(url,headers=UA,timeout=20,allow_redirects=True)
        if r.status_code!=200:return []
        raw=r.text
    except Exception:
        return []
    # Prefer visible anchor/headline text, then fall back to whole-page text.
    chunks=[]
    for m in re.finditer(r"<a\b[^>]*>(.*?)</a>",raw,flags=re.I|re.S):
        t=_clean(re.sub(r"<[^>]+>"," ",m.group(1)))
        if re.search(rf"\b(?:{ACTION_RE})\b.*?target of Rs",t,re.I):chunks.append(t)
    for m in re.finditer(r"(?:<p\b[^>]*>|<div\b[^>]*>)(.*?)</(?:p|div)>",raw,flags=re.I|re.S):
        t=_clean(re.sub(r"<[^>]+>"," ",m.group(1)))
        if re.search(rf"\b(?:{ACTION_RE})\b.*?target of Rs",t,re.I):chunks.append(t)
    if not chunks:
        text=re.sub(r"<script.*?</script>|<style.*?</style>"," ",raw,flags=re.I|re.S)
        text=re.sub(r"<[^>]+>"," ",text)
        chunks=[_clean(text)]
    out=[];seen=set()
    for chunk in chunks:
        for x in _parse_reco_text(chunk,source,url,limit):
            key=(x["symbol"],x["broker"],x["rating"],x["target_price"],x.get("date"))
            if key not in seen:seen.add(key);out.append(x)
            if len(out)>=limit:return out
    return out


def _parse_tables(url,source,limit=100):
    try:
        r=requests.get(url,headers=UA,timeout=20,allow_redirects=True)
        if r.status_code!=200:return []
        tables=pd.read_html(StringIO(r.text))
    except Exception:
        return []
    out=[]
    for df in tables:
        if df.empty:continue
        cols={_clean(c).lower():c for c in df.columns}
        def col(*names):
            for n in names:
                for k,c in cols.items():
                    if n in k:return c
            return None
        stockc=col("stock","company","company name","script","scrip")
        brokerc=col("broker","brokerage","broker / analyst","research house")
        actionc=col("action","rating","recommendation","call","reco")
        targetc=col("target price","target")
        datec=col("reco date","report dt","date","published")
        currentc=col("cmp","current price","ltp","price")
        upsidec=col("profit potential","potential","upside")
        if not stockc or not actionc or not targetc:continue
        for _,row in df.iterrows():
            company=_clean(row.get(stockc));rating=_clean(row.get(actionc));target=_num(row.get(targetc))
            if not company or not rating or target is None or not re.search(rf"\b(?:{ACTION_RE})\b",rating,re.I):continue
            current=_num(row.get(currentc)) if currentc else None;upside=_num(row.get(upsidec)) if upsidec else None
            if upside is None and target and current and current>0:upside=(target-current)/current*100
            x=_item(company,_clean(row.get(brokerc)) if brokerc else source,rating,target,_clean(row.get(datec)) if datec else None,source,url)
            x["current_price"]=current;x["upside_pct"]=round(upside,2) if upside is not None else None
            out.append(x)
            if len(out)>=limit:return out
    return out


def _parse_rss(url,limit=100):
    try:
        r=requests.get(url,headers={**UA,"Accept":"application/rss+xml,application/xml,text/xml,*/*"},timeout=20,allow_redirects=True)
        if r.status_code!=200:return []
        root=ET.fromstring(r.content)
    except Exception:
        return []
    out=[]
    for node in root.iter():
        if node.tag.lower().endswith("item"):
            vals={}
            for child in list(node):vals[child.tag.split("}")[-1].lower()]=_clean(child.text)
            title=vals.get("title","");desc=vals.get("description","")
            if re.search(rf"\b(?:{ACTION_RE})\b.*?target of Rs",title,re.I):
                out.extend(_parse_reco_text(title+" "+desc,"Moneycontrol RSS",vals.get("link") or url,limit-len(out)))
            if len(out)>=limit:break
    return out


def register_broker_routes(app,nse_get):
    router=APIRouter();cache={"ts":0.0,"items":[]}
    def collect():
        now=time.time()
        if now-cache["ts"]<900 and cache["items"]:return cache["items"]
        feeds=[
            ("Moneycontrol table","https://www.moneycontrol.com/broker-research/myStocksAll/?classic=true"),
            ("Moneycontrol latest","https://www.moneycontrol.com/broker-research/latestResearchReport/?classic=true"),
            ("Moneycontrol reports","https://www.moneycontrol.com/news/broker-research-reports-13search-reports-13.html/"),
        ]
        all_items=[];seen=set()
        for source,url in feeds:
            parsed=_parse_tables(url,source,100)
            if not parsed:parsed=_parse_html(url,source,100)
            for x in parsed:
                key=(x["symbol"],x.get("broker"),x.get("rating"),x.get("target_price"),x.get("date"))
                if key not in seen:seen.add(key);all_items.append(x)
        for url in ("https://www.moneycontrol.com/rss/latestnews.xml","https://www.moneycontrol.com/rss/marketnews.xml"):
            for x in _parse_rss(url,100):
                key=(x["symbol"],x.get("broker"),x.get("rating"),x.get("target_price"),x.get("date"))
                if key not in seen:seen.add(key);all_items.append(x)
        all_items.sort(key=lambda x:str(x.get("date") or ""),reverse=True)
        cache.update(ts=now,items=all_items);return all_items

    @router.get('/api/broker-recommendations')
    def broker_recommendations(symbol:str|None=None,limit:int=200):
        s=(symbol or '').upper().replace('.NS','');items=collect()
        if s:items=[x for x in items if x['symbol'].upper()==s or x.get('company','').upper()==s]
        return {
            'generated_at':datetime.now(timezone.utc).isoformat(),
            'items':items[:max(1,min(limit,500))],
            'data_source':'Moneycontrol public broker research listings + RSS',
            'feed_status':'live public feeds' if items else 'feeds returned no parseable public calls',
            'disclaimer':'Broker/analyst views are opinions, can change, may have conflicts, and are not guaranteed returns. StockPulse does not endorse any call. Only publicly listed source records are shown; no calls are fabricated.'
        }
    app.include_router(router)
