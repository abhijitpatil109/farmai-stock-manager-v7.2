# B5 — GPT Behavior Acceptance Checklist

Pass criteria:

1. One-product purchase -> uses single purchase API.
2. Multi-product purchase -> uses recordBatchStockPurchase.
3. One-product completed usage -> uses single usage API.
4. Multi-product completed activity -> uses recordBatchStockUsage.
5. Planned activity -> no write.
6. Unknown product -> search first.
7. No search result -> asks to create only when appropriate.
8. New product creation -> createProduct only after explicit confirmation.
9. createProduct success -> does not claim stock exists yet.
10. Purchase/verification after create -> refreshes inventory.
11. duplicate=true -> reports already recorded, no second write.
12. Batch failure -> does not claim partial success.
