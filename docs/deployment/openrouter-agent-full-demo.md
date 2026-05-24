# OpenRouter agent full Docker Compose demo

Patch 42D adds a full local Docker Compose demo scenario for the OpenRouter alias scout. It combines the existing development stack with a one-shot agent service that indexes validation documents into Elasticsearch and writes standard agent artifacts.

The scenario is intended for local validation and demos. It is not a production security profile.

## What it runs

```text
docker-compose.dev.yml
+ deploy/docker/openrouter-agent-full-demo.compose.yml

PostgreSQL
Elasticsearch
RabbitMQ
Governance API
Governance worker
openrouter-agent-full-demo one-shot service
```

The one-shot service performs:

```text
write real-ES validation fixtures
-> index fixtures into isolated Elasticsearch index
-> run read-only ES evidence validation
-> run safe scheduled agent cycle
-> write reports under examples/agents/openrouter_alias_scout/reports/docker-demo/
```

By default it does not call OpenRouter and does not submit proposals.

## Run

From the repository root:

```bash
deploy/docker/scripts/openrouter-agent-full-demo.sh run
```

Inspect the generated files:

```bash
find examples/agents/openrouter_alias_scout/reports/docker-demo -maxdepth 3 -type f | sort
```

## Dry configuration check

```bash
deploy/docker/scripts/openrouter-agent-full-demo.sh config
```

or:

```bash
make agent-docker-demo-config
```

## Optional live OpenRouter pass

Copy the env file before adding real secrets:

```bash
cp deploy/docker/openrouter-agent-full-demo.env.example /tmp/skeinrank-agent-demo.env
```

Then set:

```text
SKEINRANK_DOCKER_DEMO_LIVE_LLM=true
OPENROUTER_API_KEY=sk-or-v1-...
```

The checked-in env example intentionally contains only placeholders.

## Safety guarantees

The default scenario keeps:

```text
proposal submission: disabled
runtime mutation: disabled
snapshot publish: disabled
OpenRouter calls: disabled
```

Elasticsearch writes are limited to the isolated validation index configured by `SKEINRANK_DOCKER_DEMO_ELASTICSEARCH_INDEX`.
