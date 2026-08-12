# FarmAI B1 — Batch Purchase API

Copy `batch_purchases.py` to:

`app/api/v1/batch_purchases.py`

Then update `app/main.py`.

Add this import:

```python
from .api.v1.batch_purchases import router as batch_purchases_router
```

Add this router registration after the existing transaction router:

```python
app.include_router(batch_purchases_router)
```

Expected router block:

```python
app.include_router(health_router)
app.include_router(inventory_router)
app.include_router(products_router)
app.include_router(transactions_router)
app.include_router(batch_purchases_router)
```

New endpoint:

`POST /api/v1/inventory/purchases/batch`

Operation ID:

`recordBatchStockPurchase`

The endpoint is atomic: every item is validated before any transaction is committed.
Retrying the same batch-level idempotency key does not create duplicate stock.
