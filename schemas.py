from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field,model_validator
class StockRequest(BaseModel):
    action:Literal['recordPurchase','recordUsage','recordDamage','recordOpeningBalance','recordVerification','reverseTransaction']
    idempotency_key:str=Field(min_length=8,max_length=200)
    product_id:UUID|None=None
    product_code:str|None=None
    product_name:str|None=None
    quantity:Decimal|None=Field(default=None,gt=0)
    verified_quantity:Decimal|None=Field(default=None,ge=0)
    unit:str|None=None
    effective_at:datetime|None=None
    expiry_date:date|None=None
    batch_no:str|None=None
    reference:str|None=None
    notes:str|None=None
    recorded_by:str|None=None
    verified_by:str|None=None
    reason:str|None=None
    transaction_id:UUID|None=None
    @model_validator(mode='after')
    def validate_fields(self):
        if self.action=='reverseTransaction':
            if not self.transaction_id: raise ValueError('transaction_id is required')
            return self
        if not (self.product_id or self.product_code or self.product_name): raise ValueError('Provide product_id, product_code, or product_name')
        if self.action=='recordVerification':
            if self.verified_quantity is None: raise ValueError('verified_quantity is required')
        elif self.quantity is None: raise ValueError('quantity is required')
        return self
