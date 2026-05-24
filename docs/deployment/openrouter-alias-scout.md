# OpenRouter alias scout deployment recipe

Patch 40O adds a deployable reference recipe for the OpenRouter alias scout. The
recipe is intentionally conservative: the default Docker Compose command writes
an offline evaluation report and does not call OpenRouter, SkeinRank, or
Elasticsearch.

## Files

```text
deploy/docker/openrouter-alias-scout.Dockerfile
deploy/docker/openrouter-alias-scout.compose.yml
deploy/docker/openrouter-alias-scout.env.example
examples/agents/openrouter_alias_scout/deployment_recipe.py
```

## Inspect the recipe

From the repository root:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-deployment-recipe
```

Or write a JSON report:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-deployment-recipe examples/agents/openrouter_alias_scout/reports/deployment-recipe.json
```

The report schema is `skeinrank.agent_deployment_recipe.v1`.

## Validate Compose config

```bash
docker compose \
  --env-file deploy/docker/openrouter-alias-scout.env.example \
  -f deploy/docker/openrouter-alias-scout.compose.yml \
  config
```

Equivalent Makefile helper:

```bash
make agent-compose-config
```

## Run the safe default service

The Compose service default command is offline:

```text
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-evaluation-report examples/agents/openrouter_alias_scout/reports/evaluation-report.json
```

It does not submit proposals and does not mutate runtime snapshots.

## Live LLM review

For live review, copy the env example outside Git and provide a bounded
OpenRouter key:

```bash
cp deploy/docker/openrouter-alias-scout.env.example /tmp/openrouter-alias-scout.env
# edit /tmp/openrouter-alias-scout.env and replace CHANGE_ME values
```

Then override the command explicitly:

```bash
docker compose \
  --env-file /tmp/openrouter-alias-scout.env \
  -f deploy/docker/openrouter-alias-scout.compose.yml \
  run --rm openrouter-alias-scout \
  python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --llm-review \
  --model openai/gpt-4o-mini \
  --max-candidates 3 \
  --max-llm-calls 3 \
  --max-run-cost-usd 0.01
```

Proposal submission remains disabled in the reference config. Treat the agent as
a discovery/review worker; approved terminology changes still go through the
SkeinRank proposal, validation, review, and snapshot lifecycle.
