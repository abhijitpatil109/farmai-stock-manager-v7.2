# FarmAI V7.2 — B6 GPT Behavior Certification

Run these only AFTER `run_b6.py` passes.

Use fresh test names. Do not use real farm products unless specifically intended.

| Test | Prompt | Expected behavior |
|---|---|---|
| GPT-01 | Show current stock | Calls live inventory; V6.3 frozen layout preserved |
| GPT-02 | Purchased 5 kg <existing B6 product> | Single purchase API |
| GPT-03 | Purchased 2 kg <B6 product A> and 3 kg <B6 product B> | Batch purchase API |
| GPT-04 | We will spray tomorrow using A + B | PLAN ONLY; no inventory write |
| GPT-05 | Spray completed using A 1 kg + B 1 kg | Batch usage API |
| GPT-06 | Purchased 5 kg brand-new B6 product, category Fertilizers | Search → createProduct → purchase → refresh |
| GPT-07 | Repeat the exact previous completed purchase | Duplicate-safe; no second stock movement |
| GPT-08 | Physical stock of <B6 product> is X kg | Stock adjustment, not purchase |
| GPT-09 | Ask for transaction history of B6 product | Live transaction history |
| GPT-10 | Force/observe an API error | No false success or invented balance |

## Pass criteria

- Correct action selection.
- No write for plans/future work.
- No invented product code.
- New product is created before stock is posted.
- Multi-product operations use batch actions.
- Duplicate retries do not change stock twice.
- Failed writes are not reported as successful.
