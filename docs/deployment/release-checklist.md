# Release checklist

Use this checklist before cutting or deploying an Enterprise MVP release.

## Code and tests

```bash
cd packages/skeinrank-governance-api
poetry run python -m pytest -q
```

For deployment-focused changes, run at least:

```bash
poetry run python -m pytest \
  tests/test_production_compose_profile.py \
  tests/test_env_validation.py \
  tests/test_production_security_profile.py \
  tests/test_deployment_polish.py \
  tests/test_upgrade_runbooks.py \
  -q
```

## Compose and env

From the repository root:

```bash
make prod-env-check
make prod-config
make prod-upgrade-check
```

Before sharing a release candidate with another engineer, replace every `CHANGE_ME` secret in `.env` and make sure placeholder domains are intentional.

## Backup and migration safety

```bash
make prod-backup-export
make prod-schema-check
```

Record the backup timestamp or artifact location in the release notes.

## Runtime smoke

```bash
make prod-up
make prod-smoke
```

Use strict smoke only when optional external services are expected to be configured:

```bash
make prod-smoke-strict
```

## Observability

Check:

```bash
curl http://127.0.0.1:8010/metrics | grep -E 'skeinrank_(database_up|schema_ok)'
curl http://127.0.0.1:8010/v1/ops/troubleshooting/report | python -m json.tool
```

## Documentation

Update these docs when deployment behavior changes:

- `docs/deployment/production-compose.md`
- `docs/deployment/env-and-secrets.md`
- `docs/deployment/upgrade-guide.md`
- `docs/deployment/migration-safety.md`
- `docs/deployment/backup-restore.md`
- `docs/deployment/security.md`

## Known limitations

For Enterprise MVP releases, call out:

- portable JSON backup is for MVP/dev/pilot operations;
- native PostgreSQL backups are still recommended for real production;
- Elasticsearch/OpenSearch is optional for first bootstrap;
- `make prod-smoke-strict` requires all configured external dependencies to be reachable.
