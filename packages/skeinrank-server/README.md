# skeinrank-server

`skeinrank-server` is the **FastAPI service wrapper** for SkeinRank.

It exposes a small HTTP surface over `skeinrank-core` and an external Elasticsearch instance:

- `GET /healthz`
- `GET /diagnostics`
- `POST /v1/attributes/extract`
- `POST /v1/rerank/es`

The server does not require a repository-wide `.env` file. The attribute extraction endpoint works without Elasticsearch. In debug mode it also returns snapshot metadata and the alias matcher backend used by `skeinrank-core`. Environment variables are only needed when you actually run the HTTP service against Elasticsearch or the rerank route.

## Run tests from a source checkout

```bash
PYTHONPATH=.:../skeinrank-core pytest -q
```

## Local run

1. Make sure Elasticsearch is reachable if you want to use `/v1/rerank/es`.
2. Install the package in your preferred workflow.
3. Export the few settings the service needs.

```bash
export SKEINRANK_ES_URL="http://localhost:9200"
export SKEINRANK_ES_INDEX="kb"
export SKEINRANK_ES_TEXT_FIELD="text"
export SKEINRANK_ES_QUERY_FIELDS="text,title"
export SKEINRANK_DEFAULT_PROFILE="rerank_auto"
export SKEINRANK_DEFAULT_ATTRIBUTE_PROFILE="default_it"
```

Then run either:

```bash
skeinrank-server --host 0.0.0.0 --port 8000
```

or:

```bash
uvicorn skeinrank_server.main:app --host 0.0.0.0 --port 8000
```

Backward-compatible aliases are also supported:

- `ES_URL`
- `ES_DEFAULT_INDEX`
- `ES_TEXT_FIELD`
- `ES_QUERY_FIELDS`
- `ES_TIMEOUT_S`

## Example request: attribute extraction

```bash
curl -s http://localhost:8000/v1/attributes/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "k8s timeout on production api-server",
    "profile": "default_it",
    "debug": true
  }'
```

## Example request: rerank with Elasticsearch

```bash
curl -s http://localhost:8000/v1/rerank/es \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "okta password reset",
    "index": "kb",
    "bm25_k": 100,
    "top_k": 10,
    "profile": "rerank_auto",
    "passport": "summary"
  }'
```

## Docker

`docker-compose.yml` is included for local service runs. Elasticsearch stays external to this package.
