from fastapi import APIRouter, Query
from app.services.quality_screener import screen
import httpx
from datetime import datetime, timezone

router=APIRouter(tags=['screener'])

@router.get('/screener/top')
async def screener_top(limit:int=Query(25,ge=1,le=50),min_quality:float=Query(60,ge=0,le=100),horizon:str|None=None):
    rows=screen(limit=limit,min_quality=min_quality,horizon=horizon)
    if rows.get('items'): return rows
    from app.services.public_screener import screen_public
    return await screen_public(limit=limit)

@router.get('/market/live')
async def market_live():
    symbols={'NIFTY 50':'^NSEI','NIFTY BANK':'^NSEBANK','NIFTY IT':'^CNXIT','NIFTY MIDCAP 50':'^NSEMDCP50'}
    async def one(client,name,symbol):
        try:
            r=await client.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}',params={'range':'1d','interval':'1m','includePrePost':'false'},headers={'User-Agent':'Mozilla/5.0'})
            r.raise_for_status(); result=r.json()['chart']['result'][0]; meta=result.get('meta',{})
            price=float(meta.get('regularMarketPrice') or 0); prev=float(meta.get('chartPreviousClose') or meta.get('previousClose') or 0)
            change=((price/prev)-1)*100 if prev else 0
            return {'name':name,'symbol':symbol,'price':round(price,2),'change_pct':round(change,2),'previous_close':round(prev,2),'currency':meta.get('currency','INR'),'exchange':meta.get('exchange','NSE'),'market_state':meta.get('marketState','REGULAR')}
        except Exception:
            return None
    async with httpx.AsyncClient(timeout=8,limits=httpx.Limits(max_connections=6)) as client:
        rows=await __import__('asyncio').gather(*(one(client,n,s) for n,s in symbols.items()))
    items=[x for x in rows if x]
    return {'status':'live_market','market':'IN','generated_at':datetime.now(timezone.utc).isoformat(),'items':items,'refresh_seconds':15,'source':'Public market quote feed','note':'Quotes may be delayed depending on the public feed and exchange status.'}
