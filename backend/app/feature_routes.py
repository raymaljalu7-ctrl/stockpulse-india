from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter
import requests


def register_feature_routes(app, nse_get, current_universe):
    router=APIRouter()

    def rows(path, params=None):
        d=nse_get(path, params, 120)
        return d.get('data',[]) if isinstance(d,dict) else []

    @router.get('/api/dividends')
    def dividends(symbol: str|None=None, min_yield: float=0, limit: int=200):
        s=(symbol or '').upper().replace('.NS','')
        data=[]
        for path in ('/api/corporate-actions','/api/corporate-actions?index=equities'):
            try:
                d=nse_get(path, {'index':'equities'} if '?' not in path else None, 120)
                data=d.get('data',[]) if isinstance(d,dict) else []
                if data: break
            except Exception: pass
        out=[]
        for x in data:
            sym=str(x.get('symbol') or x.get('symbolName') or '').upper()
            purpose=str(x.get('subject') or x.get('purpose') or '')
            if s and sym!=s: continue
            if 'dividend' not in purpose.lower(): continue
            out.append({'symbol':sym,'purpose':purpose,'ex_date':x.get('exDate') or x.get('exdate'),'record_date':x.get('recordDate') or x.get('recorddate'),'bc_start_date':x.get('bcStartDate'),'bc_end_date':x.get('bcEndDate'),'dividend':x.get('dividend') or x.get('amount'),'source':'NSE corporate actions'})
        return {'generated_at':datetime.now(timezone.utc).isoformat(),'items':out[:max(1,min(limit,500))],'filters':{'symbol':s,'min_yield':min_yield},'data_source':'NSE'}

    @router.get('/api/corporate-actions')
    def corporate_actions(symbol: str|None=None, limit: int=250):
        s=(symbol or '').upper().replace('.NS',''); out=[]
        for path in ('/api/corporate-actions','/api/corporate-actions?index=equities'):
            try:
                d=nse_get(path, {'index':'equities'} if '?' not in path else None, 120)
                data=d.get('data',[]) if isinstance(d,dict) else []
                if data: break
            except Exception: data=[]
        for x in data:
            sym=str(x.get('symbol') or '').upper()
            if s and sym!=s: continue
            purpose=str(x.get('subject') or x.get('purpose') or '')
            out.append({'symbol':sym,'purpose':purpose,'ex_date':x.get('exDate') or x.get('exdate'),'record_date':x.get('recordDate') or x.get('recorddate'),'announcement_date':x.get('announcementDate'),'raw':x})
        return {'generated_at':datetime.now(timezone.utc).isoformat(),'items':out[:max(1,min(limit,500))],'data_source':'NSE'}

    @router.get('/api/board-meetings')
    def board_meetings(symbol: str|None=None, limit: int=200):
        s=(symbol or '').upper().replace('.NS',''); out=[]
        for path in ('/api/board-meetings','/api/board-meetings?index=equities'):
            try:
                d=nse_get(path, {'index':'equities'} if '?' not in path else None, 120);data=d.get('data',[]) if isinstance(d,dict) else []
                if data: break
            except Exception: data=[]
        for x in data:
            sym=str(x.get('symbol') or '').upper()
            if s and sym!=s: continue
            out.append({'symbol':sym,'purpose':x.get('purpose') or x.get('subject'),'meeting_date':x.get('meetingDate') or x.get('meeting_date'),'raw':x})
        return {'generated_at':datetime.now(timezone.utc).isoformat(),'items':out[:max(1,min(limit,500))],'data_source':'NSE'}

    @router.get('/api/shareholding/{symbol}')
    def shareholding(symbol:str):
        s=symbol.upper().replace('.NS','')
        for path in ('/api/shareholding-pattern', '/api/shareholding-pattern?index=equities'):
            try:
                d=nse_get(path, {'symbol':s} if '?' not in path else {'symbol':s}, 300)
                if isinstance(d,dict) and d.get('data'):
                    return {'symbol':s,'items':d['data'],'data_source':'NSE'}
            except Exception: pass
        return {'symbol':s,'items':[],'data_source':'NSE','message':'Shareholding feed unavailable for this symbol.'}

    @router.get('/api/analytics/{symbol}')
    def analytics(symbol:str):
        s=symbol.upper().replace('.NS',''); universe,_=current_universe(); q=next((x for x in universe if x['symbol']==s),None)
        if not q: return {'symbol':s,'error':'Stock not found'}
        p=q['price']; r30=q.get('perChange30d',0); r365=q.get('perChange365d',0); vol=q.get('volume',0)
        return {'symbol':s,'price':p,'returns':{'1D':q.get('change_pct',0),'1M':r30,'1Y':r365},'volume':{'today':vol,'signal':'High activity' if r30>3 else 'Normal activity'},'technical':{'trend':'Bullish' if r30>0 and r365>0 else 'Mixed' if r30*r365<=0 else 'Bearish','momentum_score':round(max(0,min(100,50+r30*1.5+r365*.12)),1)},'valuation':{'pe':None,'pb':None,'roe':None,'roce':None},'recommendation_engine':{'fundamental':35,'valuation':20,'technical_momentum':20,'catalyst':15,'risk':10},'note':'Weights are the StockPulse recommendation framework; unavailable fundamentals are not fabricated.'}

    @router.get('/api/trade/quote/{symbol}')
    def trade_quote(symbol:str):
        s=symbol.upper().replace('.NS',''); universe,_=current_universe();q=next((x for x in universe if x['symbol']==s),None)
        return {'symbol':s,'price':q['price'] if q else None,'buy_supported':False,'sell_supported':False,'message':'Broker execution is not connected. Use this module for order planning and portfolio tracking.'}

    app.include_router(router)
