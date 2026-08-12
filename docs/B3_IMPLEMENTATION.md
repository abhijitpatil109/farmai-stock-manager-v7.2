# FarmAI B3 — New Product Creation

## Add file
Copy `create_product.py` to:

`app/api/v1/create_product.py`

## Update `app/main.py`

Add:

```python
from .api.v1.create_product import router as create_product_router
```

Register:

```python
app.include_router(create_product_router)
```

## New endpoint

`POST /api/v1/products`

Operation ID:

`createProduct`

## Important behavior

Creating a product does **not** add stock.

Correct workflow:

1. Search product first.
2. If not found and user explicitly confirms it is a new product, call `createProduct`.
3. Then record purchase/physical verification separately.
4. Refresh live inventory.

## Request example

```json
{
  "product_code": "FERT-NEW-001",
  "product_name": "Example Fertilizer",
  "category": "Fertilizers",
  "base_unit": "kg",
  "brand": "Example Brand",
  "content": "Example content",
  "primary_function": "Example purpose",
  "notes": "Created through FarmAI"
}
```

## Required B3 tests

1. Create a unique test product.
2. Search it via `searchProducts`.
3. Read it via `getProduct`.
4. Confirm its stock is zero/no stock movement exists.
5. Retry same code → expect `PRODUCT_CODE_EXISTS`.
6. Try same name+brand with a different code → expect `PRODUCT_ALREADY_EXISTS`.
7. Try invalid category → 422.
8. Try invalid base unit → 422.
9. Add a small purchase to the test product and verify inventory.

### Note
B3 dynamically checks available `products` table columns so optional metadata
(`content`, `primary_function`, `notes`) is inserted only if those columns exist.
The table must contain at least:
`product_code`, `product_name`, `category`, `base_unit`.
