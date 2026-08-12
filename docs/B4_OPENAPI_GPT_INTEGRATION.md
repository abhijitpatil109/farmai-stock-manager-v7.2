# FarmAI B4 — OpenAPI + GPT Action Integration

B4 does not replace B1/B2/B3 Python files. Its purpose is to expose and validate
the new actions in the existing FastAPI/OpenAPI contract and GPT Action.

## Expected actions after B1+B2+B3 are registered

Existing:
- healthCheck
- getCurrentInventory
- getProductInventory
- searchProducts
- getProduct
- recordStockPurchase
- recordStockUsage
- recordStockAdjustment
- getStockTransactions

New:
- recordBatchStockPurchase
- recordBatchStockUsage
- createProduct

## 1. `main.py`

Ensure these routers are imported and registered:

```python
from .api.v1.batch_purchases import router as batch_purchases_router
from .api.v1.batch_usage import router as batch_usage_router
from .api.v1.create_product import router as create_product_router

app.include_router(batch_purchases_router)
app.include_router(batch_usage_router)
app.include_router(create_product_router)
```

## 2. Deploy

Deploy to production, then verify:

`https://farmai-stock-manager-v7-2.vercel.app/openapi.json`

The schema must contain:

- `/api/v1/inventory/purchases/batch`
- `/api/v1/inventory/issues/batch`
- `/api/v1/products`

with operation IDs:

- `recordBatchStockPurchase`
- `recordBatchStockUsage`
- `createProduct`

## 3. GPT Action

Re-import the production OpenAPI schema into the FarmAI Stock Assistant.

Keep authentication:

- API Key
- Custom Header
- `X-API-Key`
- production `FARMAI_API_KEY`

Delete/disable any obsolete action schema so the GPT cannot select legacy tools.

## 4. GPT behavior

Use single-item endpoints for one-product operations.
Use batch endpoints when one confirmed purchase/activity contains multiple products.
Use `createProduct` only after product search returns no match and the user explicitly confirms creation.

## 5. Acceptance sequence

1. `healthCheck`
2. `searchProducts`
3. B1 two-product purchase
4. Retry B1 idempotency key
5. B2 two-product usage
6. Retry B2 idempotency key
7. B2 insufficient-stock atomic rejection
8. B3 create product
9. Search new product
10. Purchase stock for new product
11. Ask GPT to perform a multi-product purchase in natural language
12. Ask GPT to perform a completed multi-product farm activity
13. Ask GPT to add a genuinely new purchased product
