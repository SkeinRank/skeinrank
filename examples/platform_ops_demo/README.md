# Platform operations demo seed

This example fills a local SkeinRank Docker Compose stack with a realistic platform-operations preview dataset.

It creates:

- an Elasticsearch index: `platform_knowledge_base`;
- 24 demo knowledge-base documents: incidents, runbooks, tickets, and design notes;
- a governance profile: `platform_ops`;
- 15 canonical terms and 29 aliases;
- global and profile stop-list entries;
- an Elasticsearch binding: `Production knowledge base`;
- pending suggestions for `EKS` and `OpenSearch`;
- evidence snapshots for suggestions;
- an enrichment job that publishes the runtime alias `platform_knowledge_base_search`.

## Start the stack

From the repository root:

```bash
ES_JAVA_OPTS="-Xms512m -Xmx512m" docker compose -f docker-compose.dev.yml up --build -d
```

Verify the API and Elasticsearch are ready:

```bash
curl -s http://127.0.0.1:8010/readyz | python3 -m json.tool
curl -s http://127.0.0.1:19200 | python3 -m json.tool
```

## Seed the demo

```bash
make demo-reset
```

`demo-reset` deletes existing demo Elasticsearch indices before loading the preview dataset. It does not delete PostgreSQL volumes or unrelated data.

For a non-destructive run:

```bash
make demo-seed
```

Check current demo status without writing data:

```bash
make demo-status
```

## Open the console

```text
http://127.0.0.1:5173
```

Default development login:

```text
admin / change-me
```

Useful demo query for Search Playground:

```text
k8s pg timeout during phoenix rollout
```

## Environment overrides

The script is local-first and refuses non-local API/Elasticsearch URLs unless explicitly overridden.

```bash
SKEINRANK_DEMO_API_URL=http://127.0.0.1:8010 \
SKEINRANK_DEMO_ELASTICSEARCH_URL=http://127.0.0.1:19200 \
SKEINRANK_DEMO_ADMIN_USERNAME=admin \
SKEINRANK_DEMO_ADMIN_PASSWORD=change-me \
make demo-reset
```

For a custom local port:

```bash
make demo-reset DEMO_ARGS="--api-url http://127.0.0.1:18010 --elasticsearch-url http://127.0.0.1:19200"
```

To seed a non-local sandbox intentionally:

```bash
python3 examples/platform_ops_demo/seed_platform_demo.py \
  --api-url https://example.invalid \
  --elasticsearch-url https://example.invalid \
  --force-non-local
```
