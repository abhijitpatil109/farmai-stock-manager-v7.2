# B6 — GPT Manual Test Matrix

Run these from the FarmAI Stock Assistant chat after backend API tests pass.

| ID | Prompt | Expected |
|---|---|---|
| GPT-01 | Show current stock | Calls live inventory; V6.3 format preserved |
| GPT-02 | Purchased Product-A 1 kg | Single purchase API |
| GPT-03 | Purchased Product-A 1 kg and Product-B 500 g | Batch purchase API |
| GPT-04 | Repeat exact previous request | Duplicate-safe; no second stock addition |
| GPT-05 | Spray planned tomorrow with A+B | No write |
| GPT-06 | Spray completed with A 10 g + B 20 ml | Batch usage API |
| GPT-07 | One batch usage item exceeds stock | No partial success claimed |
| GPT-08 | Purchased UnknownProduct 1 L | Search first; no invented product |
| GPT-09 | Confirm UnknownProduct is new | createProduct only after required fields |
| GPT-10 | New product created | Must not claim stock added |
| GPT-11 | Then purchase 1 L of new product | Purchase recorded + inventory refresh |
| GPT-12 | Physical stock is 500 ml | Adjustment, not purchase |
| GPT-13 | API returns error | No false success |
| GPT-14 | Ask transaction history | Live transaction API |
| GPT-15 | Multi-product write succeeds | One consolidated summary |
