from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx

UNIVERSE = ['RELIANCE','TCS','HDFCBANK','ICICIBANK','INFY','HINDUNILVR','ITC','SBIN','BHARTIARTL','KOTAKBANK','LT','AXISBANK','BAJFINANCE','MARUTI','M&M','SUNPHARMA','TITAN','ADANIENT','ADANIPORTS','NTPC','POWERGRID','TATASTEEL','JSWSTEEL','HCLTECH','WIPRO','TECHM','ULTRACEMCO','ASIANPAINT','NESTLEIND','TATAMOTORS','TATAELXSI','TRENT','BEL','HAL','SIEMENS','ABB','PIDILITIND','DLF','COFORGE','PERSISTENT','INDUSINDBK','BANKBARODA','CANBK','PNB','EICHERMOT','HEROMOTOCO','BAJAJ-AUTO','TVSMOTOR','DIVISLAB','DRREDDY']

def _clamp(x, lo=0.0, hi=100.0): return max(lo, min(hi, x))
def _pct(a, b): return ((a / b) - 1.0) * 100.0 if b else 0.0

def _score(closes, volumes):
    if len(closes) < 60: return {}
    last=closes[-1]
    r20=_pct(last,closes[-21]); r60=_pct(last,closes[-61]) if len(closes)>=61 else _pct(last,closes[0])
    ma20=sum(closes[-20:])/20; ma50=sum(closes[-50:])/50
    high=max(closes[-252:]); low=min(closes[-252:]); pos=_clamp((last-low)/(high-low)*100 if high!=low else 50)
    trend=100 if last>ma20>ma50 else 70 if last>ma20 else 35
    avgv=sum(volumes[-20:])/20 if len(volumes)>=20 else 0; vr=(volumes[-1]/avgv) if avgv else 1
    momentum=_clamp(50+r20*3+r60*.8)
    score=_clamp(momentum*.45+trend*.30+pos*.20+_clamp(vr*50,0,100)*.05)
    band='Strong' if score>=80 else 'Potential' if score>=70 else 'Watch' if score>=55 else 'Avoid'
    # Transparent, non-predictive reference layer: distance to the 52-week high.
    potential_up=max(0.0,_pct(high,last))
    horizon='4–8 weeks' if band=='Strong' else '6–12 weeks' if band=='Potential' else '12–24 weeks' if band=='Watch' else 'Not recommended'
    return {'price':round(last,2),'change_pct':round(_pct(last,closes[-2]),2),'return_20d_pct':round(r20,2),'return_60d_pct':round(r60,2),'ma20':round(ma20,2),'ma50':round(ma50,2),'52w_position':round(pos,1),'52w_high':round(high,2),'52w_low':round(low,2),'potential_up_pct':round(potential_up,1),'potential_basis':'Upside to 52-week high (reference, not a forecast)','potential_period':horizon,'volume_multiple':round(vr,2),'final_rank_score':round(score,1),'band':band,'verdict':'price_momentum_candidate' if score>=70 else 'watch','why':['Price above 20-day and 50-day trend levels' if trend==100 else 'Trend confirmation is mixed',f'20-day momentum {r20:+.1f}%',f'52-week range position {pos:.0f}%']}

async def screen_public(limit=25):
    async def one(client,symbol):
        try:
            r=await client.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS',params={'range':'1y','interval':'1d','events':'history'},headers={'User-Agent':'Mozilla/5.0'})
            r.raise_for_status(); data=r.json()['chart']['result'][0]; q=data['indicators']['quote'][0]
            closes=[float(x) for x in q.get('close',[]) if x is not None]; volumes=[float(x) for x in q.get('volume',[]) if x is not None]
            s=_score(closes,volumes)
            if not s:return None
            s.update({'symbol':symbol,'name':symbol,'market':'NSE'}); return s
        except Exception:return None
    async with httpx.AsyncClient(timeout=12,limits=httpx.Limits(max_connections=10)) as client:
        rows=await asyncio.gather(*(one(client,s) for s in UNIVERSE))
    items=sorted([x for x in rows if x],key=lambda x:x['final_rank_score'],reverse=True)[:limit]
    return {'status':'public_price_screen','market':'IN','exchange_scope':['NSE'],'objective':'quality_first_stock_screen','count':len(items),'generated_at':datetime.now(timezone.utc).isoformat(),'items':items,'guardrails':{'fundamental_data_available':False,'uses_live_public_price_history':True,'no_fabricated_fundamentals':True,'note':'Public mode ranks price trend and momentum only. News, filings and authorized fundamental data are separate evidence layers; reference potential is distance to the 52-week high, not a promised target.'}}
