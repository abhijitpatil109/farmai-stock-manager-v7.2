# B2 Implementation

1. Copy `batch_usage.py` to `app/api/v1/batch_usage.py`.

2. In `app/main.py` add:
```python
from .api.v1.batch_usage import router as batch_usage_router
```

3. Register:
```python
app.include_router(batch_usage_router)
```

New endpoint: `POST /api/v1/inventory/issues/batch`
Operation ID: `recordBatchStockUsage`

## Required tests
1. Deploy and confirm endpoint appears in `/openapi.json`.
2. Test one small valid usage item.
3. Verify inventory decreases once.
4. Retry identical idempotency key; expect `duplicate=true` and no second deduction.
5. Test two valid products together.
6. Test one valid + one insufficient item; expect entire batch rejected.
7. Verify neither product changes after rejected batch.
8. Verify transaction history contains crop/plot/method/activity notes.

Use canonical product codes from the Product API.
