# FarmAI V7.2 Quantity Normalization Standard

Every product has one immutable `base_unit` in the `products` table. All ledger, reservation, availability and inventory quantities are stored in that unit.

Supported conversions:

- Weight: `kg ↔ g ↔ mg`
- Volume: `l ↔ ml`

Rules:

- Weight and volume cannot be mixed.
- `bag`, `pack`, `packet`, `bottle` and similar package units are rejected until an explicit package size is modeled.
- Decimal arithmetic and three-decimal base-unit precision are used.
- A positive value that normalizes below `0.001` base units is rejected.
- Zero opening balances create no transaction and are returned as `SKIPPED_ZERO`.
- API responses include both submitted and normalized values.
