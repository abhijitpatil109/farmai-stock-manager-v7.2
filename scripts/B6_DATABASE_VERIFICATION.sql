-- FarmAI B6 verification queries
-- Replace product codes / idempotency keys before running.

-- 1. Inspect B6 transactions
SELECT
    transaction_no,
    transaction_type,
    quantity_in,
    quantity_out,
    unit,
    idempotency_key,
    status,
    created_at
FROM stock_transactions
WHERE idempotency_key LIKE 'b6-%'
ORDER BY created_at DESC;

-- 2. Ensure no duplicate idempotency keys
SELECT idempotency_key, COUNT(*)
FROM stock_transactions
GROUP BY idempotency_key
HAVING COUNT(*) > 1;

-- 3. Inspect current inventory
SELECT *
FROM current_inventory
ORDER BY category, product_name, location_code;

-- 4. Inspect B6-created products
SELECT *
FROM products
WHERE product_code LIKE 'B6-%'
ORDER BY product_code;
