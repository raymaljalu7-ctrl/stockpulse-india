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

@router.get('/fno/{symbol}')
async def fno_detail(symbol:str):
    symbol=symbol.upper().strip().replace('.NS','')
    url='https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi'
    params={'functionName':'getSymbolDerivativesData','symbol':symbol}
    headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36','Accept':'application/json,text/plain,*/*','Referer':'https://www.nseindia.com/'}
    try:
        async with httpx.AsyncClient(timeout=10,follow_redirects=True,headers=headers) as client:
            home=await client.get('https://www.nseindia.com/',headers=headers)
            if home.status_code>=400: return {'status':'unavailable','symbol':symbol,'message':'NSE session unavailable'}
            r=await client.get(url,params=params)
            r.raise_for_status(); payload=r.json()
        raw=payload.get('data',payload)
        if isinstance(raw,dict): raw=raw.get('data',[]) or raw.get('records',[]) or []
        if not isinstance(raw,list): raw=[]
        rows=[]
        for x in raw:
            if not isinstance(x,dict): continue
            oi=x.get('openInterest',x.get('open_interest'))
            vol=x.get('totalTradedVolume',x.get('total_traded_volume'))
            chg=x.get('changeinOpenInterest',x.get('changeInOpenInterest',x.get('change_in_open_interest')))
            lp=x.get('lastPrice',x.get('last_price'))
            rows.append({'instrument_type':x.get('instrumentType'),'expiry_date':x.get('expiryDate'),'last_price':lp,'open_interest':oi,'volume':vol,'change_in_open_interest':chg,'underlying_value':x.get('underlyingValue')})
        return {'status':'ok','symbol':symbol,'items':rows,'note':'F&O positioning is an inference from price/OI behaviour, not proof of participant intent.'}
    except Exception as e:
        return {'status':'unavailable','symbol':symbol,'items':[],'message':'F&O data temporarily unavailable from NSE public endpoint.'}
