from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

class AvailabilityRequest(BaseModel):
    product_code: str
    required_quantity: Decimal = Field(gt=0)
    unit: str
    required_date: date | None = None

class TransactionRequest(BaseModel):
    action: Literal[
        "recordOpeningBalance", "recordPurchase", "recordUsage",
        "recordDamage", "recordExpiryDisposal", "recordVerification",
        "reverseTransaction"
    ]
    idempotency_key: str = Field(min_length=8)
    product_code: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    verified_quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = None
    location_code: str = "MAIN"
    batch_number: str | None = None
    expiry_date: date | None = None
    effective_at: datetime | None = None
    notes: str | None = None
    external_task_id: str | None = None
    external_activity_id: str | None = None
    transaction_id: UUID | None = None

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "reverseTransaction":
            if not self.transaction_id:
                raise ValueError("transaction_id is required")
        elif self.action == "recordVerification":
            if not self.product_code or self.verified_quantity is None:
                raise ValueError("product_code and verified_quantity are required")
        elif not self.product_code or self.quantity is None:
            raise ValueError("product_code and quantity are required")
        return self

class ReservationRequest(BaseModel):
    task_id: str
    product_code: str
    quantity: Decimal = Field(gt=0)
    unit: str
    idempotency_key: str = Field(min_length=8)
    required_date: date | None = None

class ReleaseRequest(BaseModel):
    reservation_id: UUID
    idempotency_key: str = Field(min_length=8)
