# Backup/restore verified scenario

This guide provides a disposable backup/restore drill for first-company pilot
operators. It verifies the portable JSON backup path end-to-end without touching
a live
pilot database.

The drill creates two local SQLite databases under an ignored reports directory:

```text
examples/pilots/reports/backup-restore-drill/
  source-governance.db
  restored-governance.db
  governance-backup.json
  backup-restore-drill-report.json
```

## What the drill verifies

The run command performs this sequence:

1. Create a migrated source governance database.
2. Seed representative pilot data:
   - terminology profile;
   - canonical term;
   - alias;
   - Elasticsearch binding config;
   - pending governance proposal;
   - published snapshot row;
   - completed agent run row.
3. Export a portable JSON backup with the existing backup helper.
4. Inspect the backup file.
5. Create a migrated target governance database.
6. Run restore dry-run validation.
7. Restore with `--replace --yes` into the target database.
8. Verify row counts and representative values in the restored database.

This is a verification drill for the backup/restore path. It is not a native
PostgreSQL disaster-recovery replacement.

## Safety

The drill is intentionally local and read/write only against disposable SQLite
files:

```text
OpenRouter calls: false
Elasticsearch calls: false
Live database used: false
Runtime mutation: false
Generated artifacts committed by default: false
```

Generated files live under `examples/pilots/reports/`, which is ignored by git.

## Commands

From the repository root:

```bash
make backup-restore-drill-plan
make backup-restore-drill-run
make backup-restore-drill-inspect
```

Clean generated local artifacts:

```bash
make backup-restore-drill-clean
```

Direct CLI usage from `packages/skeinrank-governance-api`:

```bash
poetry run python -m skeinrank_governance_api.backup_restore_drill plan \
  --work-dir ../../examples/pilots/reports/backup-restore-drill

poetry run python -m skeinrank_governance_api.backup_restore_drill run \
  --work-dir ../../examples/pilots/reports/backup-restore-drill \
  --reset

poetry run python -m skeinrank_governance_api.backup_restore_drill inspect \
  --file ../../examples/pilots/reports/backup-restore-drill/backup-restore-drill-report.json
```

## Expected result

The final report should have:

```json
{
  "status": "verified",
  "verification": {
    "counts_match": true,
    "representative_values_match": true
  }
}
```

Representative values include the seeded profile, `kubernetes`, `k8s`, the dry-run
binding, the pending `kube` proposal, the snapshot version, and the agent run id.

## When to run it

Run the drill:

- before a first-company pilot handoff;
- before and after backup/restore code changes;
- before production-like upgrades;
- when collecting support evidence for backup/restore readiness.

For production PostgreSQL deployments, still keep native backups such as
`pg_dump --format=custom` in addition to this portable JSON drill.
