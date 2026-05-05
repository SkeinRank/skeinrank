# skeinrank-ui

SkeinRank Governance Console UI.

This package is the first frontend layer for the governance platform. It reads profiles, terms, aliases, and runtime snapshots from `packages/skeinrank-governance-api`, and provides the MVP forms for creating canonical terms and aliases.

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

The governance console currently includes:

- app shell
- profile selector
- terms table with row selection
- term details panel
- create canonical term form
- create alias form
- aliases display
- snapshot export panel
- light/dark/system theme toggle with local persistence
- API state management through TanStack Query

It intentionally does not yet implement edit/delete actions, authentication, approval flow, or realtime collaboration.

## Checks

```bash
npm run typecheck
npm test -- --run
npm run build
```
