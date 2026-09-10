from fastapi import APIRouter, Query
from app.services.quality_screener import screen

router=APIRouter(tags=['screener'])

@router.get('/screener/top')
async def screener_top(limit:int=Query(25,ge=1,le=50),min_quality:float=Query(60,ge=0,le=100),horizon:str|None=None):
    rows=screen(limit=limit,min_quality=min_quality,horizon=horizon)
    if rows.get('items'): return rows
    from app.services.public_screener import screen_public
    return await screen_public(limit=limit)
