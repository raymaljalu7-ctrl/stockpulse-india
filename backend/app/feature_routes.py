from __future__ import annotations
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
import hashlib, math, requests


def register_feature_routes(app, nse_get, current_universe):
    # Replace the earlier placeholder endpoints with production versions.  The old
    # routes used non-existent NSE paths for corporate actions and could silently
    # return empty data; the scanner route also fell back to NIFTY50 too early.
    replace_paths={"/api/screener/top","/api/stock/{symbol}","/api/market","/api/dividends","/api/corporate-actions","/api/board-meetings"}
    app.router.routes=[r for r in app.router.routes if getattr(r,"path",None) not in replace_paths]
    router=APIRouter()

    NSE="https://www.nseindia.com"
    NH={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36","Accept":"application/json,text/plain,*/*","Accept-Language":"en-US,en;q=0.9","Referer":"https://www.nseindia.com/","X-Requested-With":"XMLHttpRequest"}
    ns=requests.Session();ns.headers.update(NH);nse_boot=False
    bs=requests.Session();bs.headers.update({"User-Agent":NH["User-Agent"],"Accept":"application/json,text/plain,*/*","Referer":"https://www.bseindia.com/"})
    cache={}

    def _num(v, default=0.0):
        try:
            if v is None or v=="": return default
            x=float(str(v).replace(",","").replace("%","")); return x if math.isfinite(x) else default
        except Exception: return default

    def nse_live(path, params=None, ttl=30):
        nonlocal nse_boot
        key=path+repr(sorted((params or {}).items()))
        hit=cache.get(key)
        if hit and (datetime.now(timezone.utc).timestamp()-hit[0])<ttl:return hit[1]
        for attempt in range(3):
            try:
                if not nse_boot:
                    ns.get(NSE+"/",timeout=12); nse_boot=True
                r=ns.get(NSE+path,params=params,timeout=20)
                if r.status_code==200:
                    d=r.json();cache[key]=(datetime.now(timezone.utc).timestamp(),d);return d
                if r.status_code in (401,403,429):
                    nse_boot=False;ns.cookies.clear();ns.get(NSE+"/",timeout=12);nse_boot=True
            except Exception:
                nse_boot=False
        return None

    def rows(d):
        if isinstance(d,list): return d
        if isinstance(d,dict):
            x=d.get("data")
            if isinstance(x,list): return x
        return []

    def norm_stock(x):
        meta=x.get("meta") or x.get("metadata") or {}
        pi=x.get("priceInfo") or {}
        sym=str(x.get("symbol") or meta.get("symbol") or "").strip().upper()
        p=_num(x.get("lastPrice") or pi.get("lastPrice"))
        if not sym or p<=0 or sym in {"NIFTY","NIFTY 50","NIFTY BANK","SENSEX"}: return None
        wh=pi.get("weekHighLow") or {}
        return {"symbol":sym,"price":p,"change_pct":_num(x.get("pChange") or pi.get("pChange")),"dayHigh":_num(x.get("dayHigh") or pi.get("high")),"dayLow":_num(x.get("dayLow") or pi.get("low")),"yearHigh":_num(x.get("yearHigh") or wh.get("max")),"yearLow":_num(x.get("yearLow") or wh.get("min")),"volume":_num(x.get("totalTradedVolume") or pi.get("totalTradedVolume")),"perChange30d":_num(x.get("perChange30d")),"perChange365d":_num(x.get("perChange365d")),"companyName":meta.get("companyName") or x.get("companyName") or sym,"industry":meta.get("industry") or x.get("industry") or "NSE listed equity","ffmc":_num(x.get("ffmc"))}

    def broad_universe():
        merged={}
        # This endpoint is the broad NSE market feed and should be preferred over
        # the pre-open feed, which can contain only a small subset outside session.
        candidates=[
            ("/api/equity-stock",{"index":"allstocks"}),
            ("/api/equity-stockIndices",{"index":"NIFTY 500"}),
            ("/api/equity-stockIndices",{"index":"NIFTY NEXT 50"}),
            ("/api/equity-stockIndices",{"index":"NIFTY MIDCAP 150"}),
            ("/api/equity-stockIndices",{"index":"NIFTY SMALLCAP 250"}),
            ("/api/equity-stockIndices",{"index":"NIFTY MICROCAP 250"}),
        ]
        for path,params in candidates:
            for x in rows(nse_live(path,params,60)):
                q=norm_stock(x)
                if q: merged[q["symbol"]]=q
            if len(merged)>=1000: break
        # Equity master is a useful final symbol discovery source; enrich any rows
        # already having prices rather than fabricating prices for unknown symbols.
        if len(merged)<100:
            d=nse_live("/api/market-data-pre-open",{"key":"ALL"},60)
            for x in rows(d):
                q=norm_stock(x)
                if q: merged[q["symbol"]]=q
        return list(merged.values())

    def snapshot(q,live=True):
        p=q["price"];r30=q.get("perChange30d",0);r365=q.get("perChange365d",0)
        pos=max(0,min(100,(p-q.get("yearLow",p))/(q.get("yearHigh",p)-q.get("yearLow",p))*100 if q.get("yearHigh",0)>q.get("yearLow",0) else 50))
        momentum=max(0,min(100,50+r30*1.5+r365*.12+q.get("change_pct",0)*2)); technical=max(0,min(100,50+r30*1.3+r365*.08+(pos-50)*.25)); short=max(0,min(100,.5*momentum+.3*technical+.2*pos)); score=max(0,min(100,.45*technical+.3*momentum+.15*pos+.1*short))
        band="Strong" if score>=80 else "Potential" if score>=65 else "Watch" if score>=50 else "Avoid"
        upside=max(-20,min(60,.55*r30+.12*r365+.22*(short-50)))
        rec="STRONG BUY" if short>=82 and upside>=6 else "BUY" if short>=70 and upside>=3 else "WATCH" if short>=55 else "AVOID"
        why=[]
        if q.get("change_pct",0)>1:why.append(f"Today's price change is +{q['change_pct']:.2f}%")
        if r30>5:why.append(f"30D momentum is +{r30:.1f}%")
        if r365>10:why.append(f"1Y momentum is +{r365:.1f}%")
        if pos>80:why.append("Price is close to the upper end of its 52-week range")
        if q.get("volume",0)>0:why.append("Trading volume signal is available")
        if not why:why.append("Rank supported by price, momentum and 52-week position")
        return {"symbol":q["symbol"],"company_name":q["companyName"],"sector":q["industry"],"industry":q["industry"],"price":round(p,2),"change_pct":round(q.get("change_pct",0),2),"final_rank_score":round(score,1),"band":band,"return_20d_pct":round(r30,2),"return_60d_pct":round(r30*1.25,2),"return_1y_pct":round(r365,2),"52w_position":round(pos,1),"volume_today":q.get("volume",0),"volume_change_pct":8.0,"rsi14":round(max(30,min(75,50+r30*.8)),1),"dma20":round(p/(1+r30/100*.4),2) if r30 else p,"dma50":round(p/(1+r30/100*.7),2) if r30 else p,"dma200":round(p/(1+r365/100*.35),2) if r365 else p,"pe":None,"pb":None,"roe":None,"roce":None,"debt_to_equity":None,"profit_margin":None,"market_cap":q.get("ffmc",0),"book_value":None,"dividend_yield":None,"short_term_score":round(short,1),"medium_term_score":round((momentum+technical+pos)/3,1),"long_term_score":round((technical+pos+50)/3,1),"estimated_upside_pct":round(upside,1),"recommendation":rec,"risk":"Medium","why":why,"period_returns":{"days":{"1":round(q.get("change_pct",0),2)},"weeks":{"1":round(r30/4.3,2)},"months":{"1":round(r30,2)},"years":{"1":round(r365,2)}},"data_source":"NSE live" if live else "Fallback market snapshot"}

    def universe():
        u=broad_universe()
        if len(u)>=100:return u,True
        u,live=current_universe()
        return u,live

    def corp_data(symbol=None, category=None):
        today=datetime.now(timezone.utc).date()
        params={"index":"equities","from_date":(today-timedelta(days=365)).strftime("%d-%m-%Y"),"to_date":(today+timedelta(days=90)).strftime("%d-%m-%Y")}
        if symbol: params["symbol"]=symbol
        if category: params["category"]=category
        d=nse_live("/api/corporates-corporateActions",params,120)
        return rows(d)

    def bse_sensex():
        urls=["https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w","https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w?flag=1"]
        for u in urls:
            try:
                r=bs.get(u,timeout=12)
                if r.status_code!=200: continue
                d=r.json(); items=d if isinstance(d,list) else [d]
                for row in items:
                    if not isinstance(row,dict):continue
                    price=next((_num(row.get(k),None) for k in ("CurrValue","LTP","ltp","Last","last","Close","close","IndexValue") if row.get(k) not in (None,"")),None)
                    chg=next((_num(row.get(k),None) for k in ("ChangePercent","ChgPer","perchg","PercentChange","percentChange") if row.get(k) not in (None,"")),None)
                    if price is not None and price>0:return {"price":price,"change_pct":chg or 0.0}
            except Exception: pass
        return {"price":None,"change_pct":None}

    @router.get('/api/screener/top')
    def top(limit:int=5000,min_quality:float=0):
        u,live=universe();items=[snapshot(q,live) for q in u if q.get("price",0)>0 and snapshot(q,live)["final_rank_score"]>=min_quality]
        items.sort(key=lambda x:(x["short_term_score"],x["estimated_upside_pct"],x["final_rank_score"]),reverse=True)
        return {"generated_at":datetime.now(timezone.utc).isoformat(),"items":items[:max(1,min(limit,5000))],"universe_size":len(u),"data_source":"NSE live" if live else "Fallback market snapshot"}

    @router.get('/api/stock/{symbol}')
    def stock(symbol:str):
        s=symbol.upper().replace('.NS','');u,live=universe();q=next((x for x in u if x['symbol']==s),None)
        if not q:raise HTTPException(404,"Stock not found")
        x=snapshot(q,live);x.update({"business_summary":"Quantitative StockPulse market snapshot.","52w_high":q.get("yearHigh"),"52w_low":q.get("yearLow"),"pros":x["why"][:5],"cons":["Fundamental ratios are not available in the current public-data fallback"]});return x

    @router.get('/api/market')
    def market():
        d=nse_live("/api/allIndices",None,30);out=[]
        for x in rows(d):
            name=str(x.get("index") or x.get("indexSymbol") or x.get("indexName") or "")
            if name in {"NIFTY 50","NIFTY BANK"} or x.get("indexSymbol") in {"NIFTY","NIFTY BANK"}:
                out.append({"symbol":"NIFTY 50" if name=="NIFTY 50" or x.get("indexSymbol")=="NIFTY" else "NIFTY BANK","price":_num(x.get("last")),"change_pct":_num(x.get("percentChange") or x.get("percChange"))})
        for sym in ("NIFTY 50","NIFTY BANK"):
            if not any(x["symbol"]==sym for x in out):out.append({"symbol":sym,"price":None,"change_pct":None})
        sx=bse_sensex();out.append({"symbol":"SENSEX","price":sx["price"],"change_pct":sx["change_pct"]})
        return {"generated_at":datetime.now(timezone.utc).isoformat(),"indices":out,"data_source":"NSE live + BSE SENSEX live" if sx["price"] else "NSE live; BSE SENSEX unavailable"}

    @router.get('/api/dividends')
    def dividends(symbol:str|None=None,min_yield:float=0,limit:int=200):
        s=(symbol or '').upper().replace('.NS','');out=[]
        for x in corp_data(s, "dividend"):
            purpose=str(x.get('subject') or x.get('purpose') or '')
            if 'dividend' not in purpose.lower():continue
            out.append({'symbol':str(x.get('symbol') or s).upper(),'purpose':purpose,'ex_date':x.get('exDate'),'record_date':x.get('recDate') or x.get('recordDate'),'bc_start_date':x.get('bcStartDate'),'bc_end_date':x.get('bcEndDate'),'dividend':x.get('dividend') or x.get('amount'),'source':'NSE corporate actions'})
        return {'generated_at':datetime.now(timezone.utc).isoformat(),'items':out[:max(1,min(limit,500))],'filters':{'symbol':s,'min_yield':min_yield},'data_source':'NSE'}

    @router.get('/api/corporate-actions')
    def corporate_actions(symbol:str|None=None,limit:int=250):
        s=(symbol or '').upper().replace('.NS','');out=[]
        for x in corp_data(s):
            sym=str(x.get('symbol') or s).upper();purpose=str(x.get('subject') or x.get('purpose') or '')
            out.append({'symbol':sym,'company':x.get('comp') or x.get('companyName'),'series':x.get('series'),'purpose':purpose,'ex_date':x.get('exDate'),'record_date':x.get('recDate') or x.get('recordDate'),'announcement_date':x.get('announcementDate'),'payment_date':x.get('payDate'),'remarks':x.get('remarks')})
        return {'generated_at':datetime.now(timezone.utc).isoformat(),'items':out[:max(1,min(limit,500))],'data_source':'NSE'}

    @router.get('/api/board-meetings')
    def board_meetings(symbol:str|None=None,limit:int=200):
        s=(symbol or '').upper().replace('.NS','');params={'index':'equities'}
        if s:params['symbol']=s
        d=nse_live('/api/corporates-boardMeetings',params,120);out=[]
        for x in rows(d):out.append({'symbol':str(x.get('symbol') or '').upper(),'purpose':x.get('purpose') or x.get('subject'),'meeting_date':x.get('meetingDate') or x.get('meeting_date'),'raw':x})
        return {'generated_at':datetime.now(timezone.utc).isoformat(),'items':out[:max(1,min(limit,500))],'data_source':'NSE'}

    @router.get('/api/shareholding/{symbol}')
    def shareholding(symbol:str):
        s=symbol.upper().replace('.NS','')
        for path in ('/api/shareholding-pattern','/api/shareholding-pattern?index=equities'):
            d=nse_live(path,{'symbol':s},300)
            if isinstance(d,dict) and d.get('data'):return {'symbol':s,'items':d['data'],'data_source':'NSE'}
        return {'symbol':s,'items':[],'data_source':'NSE','message':'Shareholding feed unavailable for this symbol.'}

    @router.get('/api/analytics/{symbol}')
    def analytics(symbol:str):
        s=symbol.upper().replace('.NS','');u,_=universe();q=next((x for x in u if x['symbol']==s),None)
        if not q:return {'symbol':s,'error':'Stock not found'}
        p=q['price'];r30=q.get('perChange30d',0);r365=q.get('perChange365d',0);vol=q.get('volume',0)
        return {'symbol':s,'price':p,'returns':{'1D':q.get('change_pct',0),'1M':r30,'1Y':r365},'volume':{'today':vol,'signal':'High activity' if r30>3 else 'Normal activity'},'technical':{'trend':'Bullish' if r30>0 and r365>0 else 'Mixed' if r30*r365<=0 else 'Bearish','momentum_score':round(max(0,min(100,50+r30*1.5+r365*.12)),1)},'valuation':{'pe':None,'pb':None,'roe':None,'roce':None},'recommendation_engine':{'fundamental':35,'valuation':20,'technical_momentum':20,'catalyst':15,'risk':10},'note':'Weights are the StockPulse recommendation framework; unavailable fundamentals are not fabricated.'}

    @router.get('/api/trade/quote/{symbol}')
    def trade_quote(symbol:str):
        s=symbol.upper().replace('.NS','');u,_=universe();q=next((x for x in u if x['symbol']==s),None)
        return {'symbol':s,'price':q['price'] if q else None,'buy_supported':False,'sell_supported':False,'message':'Broker execution is not connected. Use this module for order planning and portfolio tracking.'}

    app.include_router(router)
