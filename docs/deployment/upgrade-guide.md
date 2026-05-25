# Production-ish upgrade guide

Patch 46C defines the safe upgrade path for the Docker Compose based Enterprise MVP track.

The goal is not to hide migrations behind magic. The goal is to make the operator sequence explicit:

```text
validate env -> validate compose -> export backup -> check schema -> upgrade -> smoke test -> keep rollback notes
```

This guide assumes the production-oriented stack from `docker-compose.prod.yml` and an env file created from `.env.production.example`.

## Upgrade commands

From the repository root:

```bash
make prod-env-check
make prod-config
make prod-preflight
make prod-upgrade
make prod-post-upgrade-smoke
```

The same flow can be run in smaller steps:

```bash
make prod-env-check
make prod-config
make prod-backup-export
make prod-schema-check
make prod-up
make prod-smoke
```

For a non-mutating pre-check that only validates `.env` and Compose syntax:

```bash
make prod-upgrade-check
```

For strict readiness after the upgrade, for example when Elasticsearch/OpenSearch is expected to be available:

```bash
make prod-smoke-strict
```

## Pre-upgrade checklist

1. Confirm that the working tree and deployment artifact are the version you intend to deploy.
2. Review `.env` changes against `.env.production.example` and run:

   ```bash
   make prod-env-check
   ```

3. Validate Compose rendering:

   ```bash
   make prod-config
   ```

4. Export a portable governance backup:

   ```bash
   make prod-backup-export
   ```

5. Check the current schema state:

   ```bash
   make prod-schema-check
   ```

6. Capture diagnostics if the current stack is running:

   ```bash
   curl http://127.0.0.1:8010/healthz | python -m json.tool
   curl http://127.0.0.1:8010/schema/health | python -m json.tool
   curl http://127.0.0.1:8010/metrics | grep -E 'skeinrank_(database_up|schema_ok)'
   ```

7. Pause external writers if your pilot has scheduled agents or external integrations submitting proposals.

## One-command preflight helper

The helper script wraps the common preflight sequence:

```bash
deploy/docker/scripts/prod-upgrade-preflight.sh
```

Options:

```bash
deploy/docker/scripts/prod-upgrade-preflight.sh --strict-env
deploy/docker/scripts/prod-upgrade-preflight.sh --no-backup
deploy/docker/scripts/prod-upgrade-preflight.sh --no-schema-check
```

The script uses:

```text
SKEINRANK_PROD_ENV_FILE
SKEINRANK_PROD_COMPOSE_FILE
SKEINRANK_PROD_PREFLIGHT_STRICT_ENV
```

when you need to point it to a non-default env file or compose file.

## Apply the upgrade

Run:

```bash
make prod-upgrade
```

This target runs:

```text
prod-preflight
prod-up
prod-post-upgrade-smoke
```

`prod-up` runs the one-shot `governance-migrate` service before `governance-api` and `governance-worker` become healthy.

## Post-upgrade verification

At minimum:

```bash
make prod-smoke
make prod-schema-check
curl http://127.0.0.1:8010/readyz | python -m json.tool
curl http://127.0.0.1:8010/v1/ops/troubleshooting/report | python -m json.tool
```

If Elasticsearch/OpenSearch is intentionally configured, use strict readiness:

```bash
make prod-smoke-strict
```

Expected safe state:

```text
/healthz.status = ok
/schema/health.ok = true
schema.current_matches_head = true
skeinrank_database_up = 1
skeinrank_schema_ok = 1
```

`/readyz` may be `degraded` during first bootstrap if search is not configured. That is expected when `SKEINRANK_GOVERNANCE_API_ELASTICSEARCH_URL=` is empty.

## Rollback notes

Rollback is deployment-specific. Keep these rules:

1. Do not restore over a live database while writers are running.
2. Prefer native PostgreSQL backups for real production rollback.
3. Use portable JSON backup restore for MVP/dev/pilot recovery or support reproduction.
4. Before destructive restore, run:

   ```bash
   python -m skeinrank_governance_api.backup_restore restore \
     --file backups/pre-upgrade-governance.json \
     --dry-run
   ```

5. Destructive restore requires both flags:

   ```bash
   --replace --yes
   ```

6. After rollback or restore, run:

   ```bash
   make prod-schema-check
   make prod-smoke
   ```

## When not to upgrade

Stop and investigate if any of these fail before the upgrade:

```text
make prod-env-check
make prod-config
make prod-backup-export
make prod-schema-check
```

Common blockers:

- `.env` still contains `CHANGE_ME` secrets;
- `.env` still points Elasticsearch to `https://elasticsearch.example.com:9200`;
- schema is not at Alembic head;
- portable backup cannot be exported;
- Compose config cannot render.
