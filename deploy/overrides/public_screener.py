from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx

UNIVERSE = ['RELIANCE','TCS','HDFCBANK','ICICIBANK','INFY','HINDUNILVR','ITC','SBIN','BHARTIARTL','KOTAKBANK','LT','AXISBANK','BAJFINANCE','MARUTI','M&M','SUNPHARMA','TITAN','ADANIENT','ADANIPORTS','NTPC','POWERGRID','TATASTEEL','JSWSTEEL','HCLTECH','WIPRO','TECHM','ULTRACEMCO','ASIANPAINT','NESTLEIND','TATAMOTORS','TATAELXSI','TRENT','BEL','HAL','SIEMENS','ABB','PIDILITIND','DLF','COFORGE','PERSISTENT','INDUSINDBK','BANKBARODA','CANBK','PNB','EICHERMOT','HEROMOTOCO','BAJAJ-AUTO','TVSMOTOR','DIVISLAB','DRREDDY']

def _clamp(x, lo=0.0, hi=100.0): return max(lo, min(hi, x))
def _pct(a, b): return ((a / b) - 1.0) * 100.0 if b else 0.0

def _period_returns(closes):
    def series(max_n, step=1):
        out={}
        for n in range(1,max_n+1):
            idx=n*step
            if len(closes)>idx: out[str(n)]=round(_pct(closes[-1],closes[-1-idx]),2)
        return out
    return {'days':series(min(30,len(closes)-1),1),'weeks':series(min(12,(len(closes)-1)//5),5),'months':series(min(12,(len(closes)-1)//21),21),'years':series(min(5,(len(closes)-1)//252),252)}

def _score(closes, volumes):
    if len(closes) < 60: return {}
    last=closes[-1]
    r20=_pct(last,closes[-21]); r60=_pct(last,closes[-61]) if len(closes)>=61 else _pct(last,closes[0])
    ma20=sum(closes[-20:])/20; ma50=sum(closes[-50:])/50
    high=max(closes[-252:]); low=min(closes[-252:]); pos=_clamp((last-low)/(high-low)*100 if high!=low else 50)
    trend=100 if last>ma20>ma50 else 70 if last>ma20 else 35
    avgv=sum(volumes[-20:])/20 if len(volumes)>=20 else 0; vr=(volumes[-1]/avgv) if avgv else 1
    momentum=_clamp(50+r20*3+r60*.8)
    volume_score=_clamp(vr*50,0,100)
    short_score=_clamp(momentum*.55+trend*.30+volume_score*.15)
    long_score=_clamp(_clamp(50+r60*1.6)*.55+pos*.30+trend*.15)
    score=_clamp(short_score*.60+long_score*.40)
    band='Strong' if score>=80 else 'Potential' if score>=70 else 'Watch' if score>=55 else 'Avoid'
    potential_up=max(0.0,_pct(high,last))
    horizon='4–8 weeks' if band=='Strong' else '6–12 weeks' if band=='Potential' else '12–24 weeks' if band=='Watch' else 'Not recommended'
    volume_today=volumes[-1] if volumes else 0; volume_prev=volumes[-2] if len(volumes)>=2 else volume_today
    volume_change=volume_today-volume_prev; volume_change_pct=_pct(volume_today,volume_prev)
    v7=sum(volumes[-7:])/min(7,len(volumes)) if volumes else 0
    v7_vs=_pct(volume_today,v7)
    if volume_change_pct>=50 or v7_vs>=100: volume_signal='spike'
    elif volume_change_pct>=10: volume_signal='rising'
    elif volume_change_pct<=-10: volume_signal='falling'
    else: volume_signal='stable'
    why=['Price above 20-day and 50-day trend levels' if trend==100 else 'Trend confirmation is mixed',f'20-day momentum {r20:+.1f}%',f'52-week range position {pos:.0f}%']
    if volume_signal in ('rising','spike'): why.append(f'Daily volume {volume_change_pct:+.1f}% vs previous session')
    elif volume_signal=='falling': why.append(f'Daily volume {volume_change_pct:+.1f}% vs previous session; participation is softer')
    return {'price':round(last,2),'change_pct':round(_pct(last,closes[-2]),2),'return_20d_pct':round(r20,2),'return_60d_pct':round(r60,2),'ma20':round(ma20,2),'ma50':round(ma50,2),'52w_position':round(pos,1),'52w_high':round(high,2),'52w_low':round(low,2),'potential_up_pct':round(potential_up,1),'potential_basis':'Upside to 52-week high (reference, not a forecast)','potential_period':horizon,'volume_multiple':round(vr,2),'volume_today':round(volume_today),'volume_prev_day':round(volume_prev),'volume_change':round(volume_change),'volume_change_pct':round(volume_change_pct,2),'volume_7d_avg':round(v7),'volume_vs_7d_avg_pct':round(v7_vs,2),'volume_signal':volume_signal,'period_returns':_period_returns(closes),'short_term_score':round(short_score,1),'long_term_score':round(long_score,1),'long_term_basis':'Price-trend and range evidence only; fundamental quality is not available in public mode','final_rank_score':round(score,1),'band':band,'verdict':'price_momentum_candidate' if score>=70 else 'watch','why':why}

async def screen_public(limit=25):
    async def one(client,symbol):
        try:
            r=await client.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS',params={'range':'5y','interval':'1d','events':'history'},headers={'User-Agent':'Mozilla/5.0'})
            r.raise_for_status(); data=r.json()['chart']['result'][0]; q=data['indicators']['quote'][0]
            closes=[float(x) for x in q.get('close',[]) if x is not None]; volumes=[float(x) for x in q.get('volume',[]) if x is not None]
            s=_score(closes,volumes)
            if not s:return None
            s.update({'symbol':symbol,'name':symbol,'market':'NSE'}); return s
        except Exception:return None
    async with httpx.AsyncClient(timeout=12,limits=httpx.Limits(max_connections=10)) as client:
        rows=await asyncio.gather(*(one(client,s) for s in UNIVERSE))
    items=sorted([x for x in rows if x],key=lambda x:x['final_rank_score'],reverse=True)[:limit]
    return {'status':'public_price_screen','market':'IN','exchange_scope':['NSE'],'objective':'quality_first_stock_screen','count':len(items),'generated_at':datetime.now(timezone.utc).isoformat(),'items':items,'guardrails':{'fundamental_data_available':False,'uses_live_public_price_history':True,'no_fabricated_fundamentals':True,'note':'Public mode ranks price trend and momentum only. Long-term score is not a fundamental-quality score. News, filings and authorized fundamental data are separate evidence layers; reference potential is distance to the 52-week high, not a promised target.'}}
