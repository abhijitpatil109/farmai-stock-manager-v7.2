# FarmAI B6 — Backend + GPT Certification Tests

B6 validates B1/B2/B3/B4 behavior before production freeze.

## Test groups

### A. Batch Purchase
- valid 2-item batch;
- duplicate retry;
- invalid product atomic rejection;
- invalid unit atomic rejection.

### B. Batch Usage
- valid 2-item completed activity;
- duplicate retry;
- insufficient-stock atomic rejection;
- invalid product atomic rejection.

### C. Create Product
- successful create;
- duplicate product_code rejection;
- duplicate name+brand rejection;
- invalid category rejection;
- invalid base unit rejection;
- zero-stock-after-create behavior.

### D. OpenAPI / GPT
- required operation IDs exist;
- GPT selects batch APIs for multi-product requests;
- GPT selects createProduct only after search + explicit confirmation;
- no stock write for planned work.

## Certification rule

Production freeze only when there are:
- zero critical failures;
- zero duplicate-stock failures;
- zero partial-write failures where atomic behavior is expected;
- zero invented-product writes;
- zero false-success responses after API errors.
