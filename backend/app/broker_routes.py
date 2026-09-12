from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter

def register_broker_routes(app, nse_get):
    router=APIRouter()
    @router.get('/api/broker-recommendations')
    def broker_recommendations(symbol: str|None=None, limit: int=200):
        s=(symbol or '').upper().replace('.NS','')
        items=[]
        # Only surface records actually returned by an upstream public feed.
        for path in ('/api/analyst-recommendations','/api/broker-recommendations','/api/stock-recommendations'):
            try:
                d=nse_get(path, {'symbol':s} if s else None, 120)
                rows=d.get('data',[]) if isinstance(d,dict) else []
                if not rows: continue
                for x in rows:
                    sym=str(x.get('symbol') or x.get('symbolName') or '').upper()
                    if s and sym!=s: continue
                    items.append({'symbol':sym,'broker':x.get('broker') or x.get('brokerName') or x.get('source'),'analyst':x.get('analyst'),'rating':x.get('rating') or x.get('recommendation'),'target_price':x.get('targetPrice') or x.get('target'),'current_price':x.get('currentPrice') or x.get('ltp'),'upside_pct':x.get('upside') or x.get('upsidePct'),'horizon':x.get('horizon'),'date':x.get('date') or x.get('publishedDate'),'rationale':x.get('rationale') or x.get('reason'),'source_url':x.get('sourceUrl') or x.get('url')})
                if items: break
            except Exception: pass
        return {'generated_at':datetime.now(timezone.utc).isoformat(),'items':items[:max(1,min(limit,500))],'data_source':'Public market feed','disclaimer':'Broker/analyst views are opinions, can change, may have conflicts, and are not guaranteed returns. StockPulse does not endorse any call. If no public feed data is available, no calls are fabricated.'}
    app.include_router(router)
