# Setup

## Repository

Replace the current GitHub repository contents with the contents of this folder.

The root must contain:

- app/
- database/
- docs/
- openapi/
- requirements.txt
- vercel.json
- .env.example

## Neon

Use a clean Neon branch or database for V7.2.

Run the SQL contents in this order:

1. database/001_schema.sql
2. database/002_seed.sql

Do not type filenames into the Neon SQL Editor. Open each file and paste its SQL.

## Vercel

Import the repository and add:

- DATABASE_URL: Neon pooled connection string
- FARMAI_API_KEY: private random secret
- ENVIRONMENT: production

No Framework Preset is required.

## Test

curl -H "X-API-Key: YOUR_KEY" https://YOUR_DOMAIN/health

curl -H "X-API-Key: YOUR_KEY" https://YOUR_DOMAIN/inventory
