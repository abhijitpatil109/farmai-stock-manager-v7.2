# B5 — GPT Instruction Integration

Purpose: add only the minimum new behavior needed for B1/B2/B3 without duplicating existing V7.2/S8/S9/S10 rules.

Recommended placement:
- Put the B5 block near existing Write Operations / Product Resolution rules.
- If equivalent rules already exist, merge them instead of appending duplicates.

Do NOT duplicate:
- source-of-truth rules;
- general idempotency rules;
- existing natural-language routing;
- existing multi-product activity rules;
- existing post-write refresh rules.

The supplied B5 block is intentionally compact.
