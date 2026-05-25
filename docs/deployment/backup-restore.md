# Backup, restore, and operational runbooks

Patch 45C adds a lightweight, portable backup/restore workflow for the SkeinRank Governance API control-plane database.

The built-in backup format is JSON and SQLAlchemy-metadata driven. It is intended for local development, demos, pilot environments, and pre-upgrade safety snapshots. For large production PostgreSQL deployments, keep using native database backups such as `pg_dump`, managed database snapshots, or volume-level snapshots as the primary recovery mechanism.

## Scope

The portable backup includes governance tables known to SQLAlchemy metadata, such as profiles, terms, aliases, snapshots, bindings, suggestions, users, API tokens, agent runs, document visits, candidate observations, evidence windows, LLM reviews, and proposal attempts.

The backup does not replace:

- Elasticsearch index backups or snapshots;
- RabbitMQ queue durability/backup policy;
- object storage artifacts outside the governance DB;
- native PostgreSQL backup and PITR strategy.

## Create a backup

Run migrations first, then export a backup:

```bash
cd packages/skeinrank-governance-api

poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run python -m skeinrank_governance_api.backup_restore export \
  --out backups/skeinrank-governance-$(date +%Y%m%d-%H%M%S).json
```

You can also use the Poetry script:

```bash
poetry run skeinrank-governance-backup export \
  --out backups/skeinrank-governance-dev.json
```

The command writes a JSON document with:

- `format_version = skeinrank.governance.backup.v1`;
- generation timestamp;
- service version;
- source DB dialect;
- source schema health summary;
- per-table columns, row counts, and rows;
- warnings when the source schema is not at Alembic head.

## Inspect a backup

Before restoring, inspect the file:

```bash
poetry run python -m skeinrank_governance_api.backup_restore inspect \
  --file backups/skeinrank-governance-dev.json
```

This prints a compact summary with table names and row counts. It does not connect to a database.

## Restore into a migrated target database

Restore expects the target database schema to be already migrated to the current Alembic head:

```bash
export SKEINRANK_GOVERNANCE_API_DATABASE_URL=sqlite:///restore-target.db
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run python -m skeinrank_governance_api.migrations check
```

Validate the restore without writing:

```bash
poetry run python -m skeinrank_governance_api.backup_restore restore \
  --file backups/skeinrank-governance-dev.json \
  --dry-run
```

Restore into an empty target:

```bash
poetry run python -m skeinrank_governance_api.backup_restore restore \
  --file backups/skeinrank-governance-dev.json \
  --replace \
  --yes
```

`--replace --yes` is required when target governance tables are not empty. This is intentional: restore is destructive when replacing existing control-plane state.

## Override the target database URL

Every command uses the same database URL precedence as the API:

1. `SKEINRANK_GOVERNANCE_API_DATABASE_URL`
2. `SKEINRANK_GOVERNANCE_DATABASE_URL`
3. `sqlite:///skeinrank_governance.db`

For one-off commands, pass `--database-url`:

```bash
poetry run python -m skeinrank_governance_api.backup_restore export \
  --database-url sqlite:///source.db \
  --out backups/source.json

poetry run python -m skeinrank_governance_api.backup_restore restore \
  --database-url sqlite:///target.db \
  --file backups/source.json \
  --replace \
  --yes
```

## Operational runbook: before upgrade

1. Stop write-heavy agent jobs or scheduled proposal workers.
2. Run migrations check:

   ```bash
   poetry run python -m skeinrank_governance_api.migrations check
   ```

3. Generate a troubleshooting report:

   ```bash
   poetry run python -m skeinrank_governance_api.troubleshooting report --strict
   ```

4. Export a governance backup:

   ```bash
   poetry run python -m skeinrank_governance_api.backup_restore export \
     --out backups/pre-upgrade-governance.json
   ```

5. Inspect the backup and confirm non-zero row counts for expected tables.
6. Apply the upgrade/migrations.
7. Run `/readyz`, `/schema/health`, `/metrics`, and the troubleshooting report again.

## Operational runbook: restore drill

Run this periodically in a disposable database:

```bash
export SKEINRANK_GOVERNANCE_API_DATABASE_URL=sqlite:///restore-drill.db
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run python -m skeinrank_governance_api.backup_restore restore \
  --file backups/pre-upgrade-governance.json \
  --dry-run
poetry run python -m skeinrank_governance_api.backup_restore restore \
  --file backups/pre-upgrade-governance.json \
  --replace \
  --yes
poetry run python -m skeinrank_governance_api.troubleshooting report --strict
```

The drill should finish with `status = ok` in the troubleshooting report.

## Operational runbook: incident triage

When a pilot environment behaves unexpectedly:

1. Capture the request id from the failing API call or log line.
2. Pull readiness and schema status:

   ```bash
   curl http://127.0.0.1:8010/readyz | python -m json.tool
   curl http://127.0.0.1:8010/schema/health | python -m json.tool
   ```

3. Generate a sanitized troubleshooting report:

   ```bash
   poetry run python -m skeinrank_governance_api.troubleshooting report
   ```

4. Export a backup before destructive experiments:

   ```bash
   poetry run python -m skeinrank_governance_api.backup_restore export \
     --out backups/incident-before-fix.json
   ```

5. Check Prometheus metrics for `skeinrank_database_up`, `skeinrank_schema_ok`, and agent tracking gauges.
6. Avoid restoring over a live production database without stopping writers and taking a native DB backup first.

## Native production backup recommendation

For PostgreSQL production-like deployments, keep a native backup in addition to the portable JSON backup:

```bash
pg_dump --format=custom --file=skeinrank-governance.dump "$SKEINRANK_GOVERNANCE_API_DATABASE_URL"
```

The portable JSON backup is useful for support/debug portability and small pilot restores. Native backups remain the source of truth for production disaster recovery.


## Docker Compose production backup helper

Patch 46A adds an ops one-shot service to `docker-compose.prod.yml` that exports a timestamped portable JSON backup into the `skeinrank_postgres_backups` Docker volume:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile ops run --rm governance-backup-export
```

This helper uses the same `python -m skeinrank_governance_api.backup_restore export` command documented above. Native PostgreSQL backups remain recommended for real production disaster recovery.
