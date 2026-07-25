from fastapi import Depends,FastAPI,HTTPException,Query
from .db import db_connection
from .schemas import StockRequest
from .security import verify_api_key
from .service import get_inventory,get_history,record_movement,record_verification,reverse_transaction
app=FastAPI(title='FarmAI Stock Manager API',version='7.2.0')
@app.get('/health',dependencies=[Depends(verify_api_key)])
def health():
    with db_connection() as c:c.execute('select 1')
    return {'ok':True,'data':{'service':'FarmAI Stock Manager','version':'7.2.0','status':'ok'}}
@app.get('/inventory',dependencies=[Depends(verify_api_key)])
def inventory():
    with db_connection() as c:return {'ok':True,'data':get_inventory(c)}
@app.get('/history',dependencies=[Depends(verify_api_key)])
def history(product:str=Query(min_length=1)):
    with db_connection() as c:return {'ok':True,'data':get_history(c,product)}
@app.post('/stock',dependencies=[Depends(verify_api_key)])
def update(req:StockRequest):
    with db_connection() as c:
        try:
            if req.action=='recordPurchase':r=record_movement(c,req,'PURCHASE',True)
            elif req.action=='recordOpeningBalance':r=record_movement(c,req,'OPENING_BALANCE',True)
            elif req.action=='recordUsage':r=record_movement(c,req,'USAGE',False)
            elif req.action=='recordDamage':r=record_movement(c,req,'DAMAGE',False)
            elif req.action=='recordVerification':r=record_verification(c,req)
            elif req.action=='reverseTransaction':r=reverse_transaction(c,req)
            else: raise HTTPException(400,detail={'code':'INVALID_ACTION','message':'Unsupported action.'})
            c.commit();return {'ok':True,'data':r}
        except Exception:c.rollback();raise
