-- FarmAI V7.2 — Deactivate B6 Certification Products
--
-- Run ONLY AFTER cleanup_execute.py --confirm reports PASS.
-- This preserves product and transaction audit history while removing
-- B6 certification products from active operational inventory.

BEGIN;

-- 1. Preview exactly what will be deactivated.
SELECT
    product_code,
    product_name,
    category,
    base_unit,
    active
FROM products
WHERE product_name LIKE 'B6 CERT %'
ORDER BY product_code;

-- Review the SELECT result before continuing.

-- 2. Deactivate B6 certification products.
UPDATE products
SET active = FALSE
WHERE product_name LIKE 'B6 CERT %'
  AND active = TRUE;

-- 3. Verify.
SELECT
    product_code,
    product_name,
    active
FROM products
WHERE product_name LIKE 'B6 CERT %'
ORDER BY product_code;

COMMIT;
