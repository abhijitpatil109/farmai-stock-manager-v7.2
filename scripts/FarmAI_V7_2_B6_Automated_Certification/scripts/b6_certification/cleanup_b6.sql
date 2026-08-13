-- ============================================================
-- FarmAI V7.2 B6 CLEANUP TEMPLATE
--
-- IMPORTANT:
-- 1. Run cleanup_preview.py first.
-- 2. Replace the placeholders below with the exact B6 run prefix
--    and test product names/codes from b6_state.json.
-- 3. REVIEW the SELECT results before running any UPDATE/INSERT.
-- 4. Preserve ledger/audit history. Prefer REVERSAL + deactivation.
--
-- This file is intentionally not auto-executed by run_b6.py.
-- ============================================================

-- Example prefix:
-- b6-20260813190000-ABC123%

-- STEP A — PREVIEW B6 TRANSACTIONS
SELECT
    st.id,
    st.transaction_no,
    st.transaction_type,
    p.product_code,
    p.product_name,
    st.quantity_in,
    st.quantity_out,
    st.unit,
    st.idempotency_key,
    st.status,
    st.created_at
FROM stock_transactions st
JOIN products p ON p.id = st.product_id
WHERE st.idempotency_key LIKE 'REPLACE_B6_PREFIX%'
ORDER BY st.created_at;

-- STEP B — PREVIEW B6 PRODUCTS
SELECT *
FROM products
WHERE product_name LIKE 'B6 CERT %'
ORDER BY product_code;

-- STOP HERE and review.
--
-- Reversal SQL depends on the exact production stock_transactions schema.
-- Use your approved FarmAI REVERSAL pattern rather than DELETE.
-- After reversal, deactivate test products:
--
-- UPDATE products
-- SET active = FALSE
-- WHERE product_name LIKE 'B6 CERT %';
