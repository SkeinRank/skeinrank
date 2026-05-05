# skeinrank-ui

SkeinRank Governance Console UI skeleton.

This package is the first frontend layer for the governance platform. It is intentionally small and API-ready: it reads profiles, terms, aliases, and runtime snapshots from `packages/skeinrank-governance-api`.

## Stack

- React
- TypeScript
- Vite
- shadcn-style local UI components
- Tailwind CSS
- TanStack Query
- TanStack Table
- Light/dark/system theme toggle

## Run locally

Start the governance API first:

```bash
cd packages/skeinrank-governance-api
export SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true
poetry run skeinrank-governance-api --reload
```

Then start the UI:

```bash
cd packages/skeinrank-ui
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

If the API is not running on the default URL, set:

```bash
export VITE_SKEINRANK_GOVERNANCE_API_URL=http://127.0.0.1:8010
```

## Current scope

Patch 21 adds only the UI skeleton:

- app shell
- profile selector
- terms table
- aliases display
- snapshot export panel
- light/dark/system theme toggle with local persistence
- health/API-ready wiring through TanStack Query

It does not yet implement create/update/delete forms, authentication, approval flow, or realtime collaboration.

## Checks

```bash
npm run typecheck
npm test -- --run
npm run build
```
