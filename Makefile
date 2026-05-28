.PHONY: demo-seed demo-reset demo-status headless-up headless-down headless-reset headless-golden-path agent-demo agent-demo-report agent-eval agent-eval-report agent-deploy-plan agent-deploy-recipe agent-compose-config agent-new-alias-smoke-plan agent-new-alias-smoke-report agent-es-evidence-plan agent-es-evidence-report agent-tracking-plan agent-tracking-report agent-integration-smoke-plan agent-integration-smoke-report agent-real-es-validation-plan agent-real-es-validation-fixtures agent-real-es-validation-index agent-real-es-validation-report prod-env-check prod-env-check-strict prod-config prod-up prod-smoke prod-smoke-strict prod-down prod-schema-check prod-backup-export prod-preflight prod-upgrade-check prod-upgrade prod-post-upgrade-smoke benchmark-reset benchmark-seed benchmark-eval benchmark-report benchmark-clean benchmark-retrieval-plan benchmark-retrieval-eval benchmark-retrieval-report benchmark-retrieval-compare benchmark-retrieval-compare-report benchmark-retrieval-run benchmark-retrieval-clean benchmark-smoke-plan benchmark-smoke-generate benchmark-smoke-report benchmark-smoke-clean benchmark-stack-up benchmark-stack-wait benchmark-stack-reset benchmark-stack-seed benchmark-stack-eval benchmark-stack-report benchmark-stack-clean benchmark-stack-down benchmark-stack-prune-containers benchmark-stack-run benchmark-agent-live-plan benchmark-agent-live-check benchmark-agent-live benchmark-agent-live-validate benchmark-agent-live-full benchmark-agent-live-validated-pilot-plan benchmark-agent-live-validated-pilot benchmark-agent-live-validated-pilot-report benchmark-agent-live-validated-pilot-stack benchmark-stack-auth-token pilot-plan pilot-preflight pilot-seed pilot-eval pilot-report pilot-run pilot-stack-run agent-openrouter-pilot-plan agent-openrouter-pilot agent-openrouter-pilot-report agent-openrouter-pilot-validate agent-openrouter-validated-pilot-plan agent-openrouter-validated-pilot-report

PYTHON ?= python3
DEMO_SEED := examples/platform_ops_demo/seed_platform_demo.py
DEMO_ARGS ?=
HEADLESS_COMPOSE := docker compose --env-file deploy/docker/headless.env.example -f docker-compose.headless.yml

PROD_ENV ?= .env
PROD_ENV_ABS := $(abspath $(PROD_ENV))
PROD_COMPOSE_FILE ?= docker-compose.prod.yml
PROD_COMPOSE_FILE_ABS := $(abspath $(PROD_COMPOSE_FILE))
PROD_COMPOSE := docker compose --env-file $(PROD_ENV) -f $(PROD_COMPOSE_FILE)

BENCHMARK_DATABASE_URL ?= sqlite:///skeinrank_governance.db
BENCHMARK_REPORT ?= examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
BENCHMARK_RETRIEVAL_REPORT ?= examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-report.json
BENCHMARK_RETRIEVAL_COMPARISON_REPORT ?= examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-retrieval-comparison-report.json
BENCHMARK_SYNTHETIC_SMOKE_CORPUS ?= examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-corpus.jsonl
BENCHMARK_SYNTHETIC_SMOKE_MANIFEST ?= examples/benchmarks/platform_ops_v1/reports/synthetic/platform_ops_v1-5k-manifest.json
BENCHMARK_SYNTHETIC_SMOKE_DOCUMENTS ?= 5000
BENCHMARK_SYNTHETIC_SMOKE_BATCH_SIZE ?= 500
BENCHMARK_RETRIEVAL_TOP_K ?= 10
BENCHMARK_CLI := cd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.benchmark --database-url "$(BENCHMARK_DATABASE_URL)"
BENCHMARK_RETRIEVAL_CLI := cd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.retrieval_eval
BENCHMARK_RETRIEVAL_COMPARE_CLI := cd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.retrieval_compare
BENCHMARK_SYNTHETIC_SMOKE_CLI := cd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.synthetic_smoke

BENCHMARK_STACK_COMPOSE_FILE ?= docker-compose.dev.yml
BENCHMARK_STACK_ENV_FILE ?= deploy/docker/benchmark.env.example
BENCHMARK_STACK_COMPOSE_PROJECT ?= skeinrank-benchmark
BENCHMARK_STACK_ENV := COMPOSE_PROJECT_NAME=$(BENCHMARK_STACK_COMPOSE_PROJECT) POSTGRES_DB=app_db POSTGRES_USER=app_user POSTGRES_PASSWORD=skeinrank_dev_password RABBITMQ_DEFAULT_USER=skeinrank RABBITMQ_DEFAULT_PASS=skeinrank_dev_password SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN=true SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD=change-me GOVERNANCE_API_PORT=8010 ELASTICSEARCH_PORT=19200
BENCHMARK_STACK_COMPOSE := $(BENCHMARK_STACK_ENV) docker compose --env-file $(BENCHMARK_STACK_ENV_FILE) -p $(BENCHMARK_STACK_COMPOSE_PROJECT) -f $(BENCHMARK_STACK_COMPOSE_FILE)
BENCHMARK_STACK_DATABASE_URL ?= postgresql+psycopg://app_user:skeinrank_dev_password@127.0.0.1:15432/app_db
BENCHMARK_STACK_API_URL ?= http://127.0.0.1:8010
BENCHMARK_STACK_ES_URL ?= http://127.0.0.1:19200
BENCHMARK_STACK_ADMIN_USERNAME ?= admin
BENCHMARK_STACK_ADMIN_PASSWORD ?= change-me
BENCHMARK_STACK_REPORT ?= examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-stack-report.json
OPENROUTER_VALIDATED_PILOT_PROFILE ?= platform_ops_benchmark
OPENROUTER_VALIDATED_PILOT_REPORT ?= examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-validated-pilot-report.json
OPENROUTER_VALIDATED_PILOT_ARGS ?= --profile-name $(OPENROUTER_VALIDATED_PILOT_PROFILE) --max-candidates 2 --max-llm-calls 1 --max-proposals 2
BENCHMARK_STACK_CONTAINERS ?= skeinrank-postgres-dev skeinrank-rabbitmq-dev skeinrank-elasticsearch-dev skeinrank-governance-migrate-dev skeinrank-governance-api-dev
BENCHMARK_STACK_VOLUMES ?= skeinrank-benchmark_skeinrank_postgres_data skeinrank-benchmark_skeinrank_rabbitmq_data skeinrank-benchmark_skeinrank_elasticsearch_data
BENCHMARK_STACK_CLI := cd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.benchmark_stack --database-url "$(BENCHMARK_STACK_DATABASE_URL)" --api-url "$(BENCHMARK_STACK_API_URL)" --elasticsearch-url "$(BENCHMARK_STACK_ES_URL)" --admin-username "$(BENCHMARK_STACK_ADMIN_USERNAME)" --admin-password "$(BENCHMARK_STACK_ADMIN_PASSWORD)"
BENCHMARK_STACK_AUTH_TOKEN := $(PYTHON) -c 'import json, urllib.request; payload=json.dumps({"username":"$(BENCHMARK_STACK_ADMIN_USERNAME)","password":"$(BENCHMARK_STACK_ADMIN_PASSWORD)"}).encode(); req=urllib.request.Request("$(BENCHMARK_STACK_API_URL)/v1/auth/login", data=payload, headers={"Content-Type":"application/json","Accept":"application/json"}, method="POST"); print(json.load(urllib.request.urlopen(req))["access_token"])'

PILOT_CONFIG ?= examples/pilots/elasticsearch_pilot.example.json
PILOT_API_URL ?= http://127.0.0.1:8010
PILOT_REPORT ?= examples/pilots/reports/pilot-integration-report.json
PILOT_AUTH_ARGS ?=
PILOT_CONFIG_PATH := $(abspath $(PILOT_CONFIG))
PILOT_REPORT_PATH := $(abspath $(PILOT_REPORT))
PILOT_CLI := cd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.pilot_integration --api-url "$(PILOT_API_URL)" --config "$(PILOT_CONFIG_PATH)" --out "$(PILOT_REPORT_PATH)" $(PILOT_AUTH_ARGS)

demo-seed:
	$(PYTHON) $(DEMO_SEED) $(DEMO_ARGS)

demo-reset:
	$(PYTHON) $(DEMO_SEED) --reset $(DEMO_ARGS)

demo-status:
	$(PYTHON) $(DEMO_SEED) --status $(DEMO_ARGS)

headless-up:
	$(HEADLESS_COMPOSE) up --build -d

headless-down:
	$(HEADLESS_COMPOSE) down

headless-reset:
	$(HEADLESS_COMPOSE) down -v

headless-golden-path:
	deploy/docker/scripts/headless-golden-path.sh

prod-env-check:
	cd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.env_validation validate --file "$(PROD_ENV_ABS)"

prod-env-check-strict:
	cd packages/skeinrank-governance-api && poetry run python -m skeinrank_governance_api.env_validation validate --file "$(PROD_ENV_ABS)" --strict

prod-config:
	$(PROD_COMPOSE) config

prod-up:
	$(PROD_COMPOSE) up --build -d

prod-smoke:
	deploy/docker/scripts/prod-smoke-test.sh

prod-smoke-strict:
	deploy/docker/scripts/prod-smoke-test.sh --strict

prod-down:
	$(PROD_COMPOSE) down

prod-schema-check:
	$(PROD_COMPOSE) --profile ops run --rm governance-schema-check

prod-backup-export:
	$(PROD_COMPOSE) --profile ops run --rm governance-backup-export

prod-preflight:
	SKEINRANK_PROD_ENV_FILE="$(PROD_ENV_ABS)" SKEINRANK_PROD_COMPOSE_FILE="$(PROD_COMPOSE_FILE_ABS)" deploy/docker/scripts/prod-upgrade-preflight.sh

prod-upgrade-check:
	SKEINRANK_PROD_ENV_FILE="$(PROD_ENV_ABS)" SKEINRANK_PROD_COMPOSE_FILE="$(PROD_COMPOSE_FILE_ABS)" deploy/docker/scripts/prod-upgrade-preflight.sh --no-backup --no-schema-check

prod-upgrade:
	$(MAKE) prod-preflight PROD_ENV="$(PROD_ENV)" PROD_COMPOSE_FILE="$(PROD_COMPOSE_FILE)"
	$(PROD_COMPOSE) up --build -d
	$(MAKE) prod-post-upgrade-smoke

prod-post-upgrade-smoke:
	deploy/docker/scripts/prod-smoke-test.sh

benchmark-reset:
	$(BENCHMARK_CLI) reset

benchmark-seed:
	$(BENCHMARK_CLI) seed

benchmark-eval:
	$(BENCHMARK_CLI) eval --out ../../$(BENCHMARK_REPORT)

benchmark-report:
	$(BENCHMARK_CLI) report --file ../../$(BENCHMARK_REPORT)

benchmark-clean:
	rm -f $(BENCHMARK_REPORT)
	$(BENCHMARK_CLI) reset

benchmark-retrieval-plan:
	$(BENCHMARK_RETRIEVAL_CLI) plan --top-k $(BENCHMARK_RETRIEVAL_TOP_K)

benchmark-retrieval-eval:
	$(BENCHMARK_RETRIEVAL_CLI) eval --top-k $(BENCHMARK_RETRIEVAL_TOP_K) --out ../../$(BENCHMARK_RETRIEVAL_REPORT)

benchmark-retrieval-report:
	$(BENCHMARK_RETRIEVAL_CLI) report --file ../../$(BENCHMARK_RETRIEVAL_REPORT)

benchmark-retrieval-compare:
	$(BENCHMARK_RETRIEVAL_COMPARE_CLI) compare --input ../../$(BENCHMARK_RETRIEVAL_REPORT) --out ../../$(BENCHMARK_RETRIEVAL_COMPARISON_REPORT)

benchmark-retrieval-compare-report:
	$(BENCHMARK_RETRIEVAL_COMPARE_CLI) report --file ../../$(BENCHMARK_RETRIEVAL_COMPARISON_REPORT)

benchmark-retrieval-run: benchmark-retrieval-eval benchmark-retrieval-compare benchmark-retrieval-compare-report

benchmark-retrieval-clean:
	rm -f $(BENCHMARK_RETRIEVAL_REPORT)
	rm -f $(BENCHMARK_RETRIEVAL_COMPARISON_REPORT)

benchmark-smoke-plan:
	$(BENCHMARK_SYNTHETIC_SMOKE_CLI) plan --documents $(BENCHMARK_SYNTHETIC_SMOKE_DOCUMENTS) --batch-size $(BENCHMARK_SYNTHETIC_SMOKE_BATCH_SIZE)

benchmark-smoke-generate:
	$(BENCHMARK_SYNTHETIC_SMOKE_CLI) generate --documents $(BENCHMARK_SYNTHETIC_SMOKE_DOCUMENTS) --batch-size $(BENCHMARK_SYNTHETIC_SMOKE_BATCH_SIZE) --out ../../$(BENCHMARK_SYNTHETIC_SMOKE_CORPUS) --manifest ../../$(BENCHMARK_SYNTHETIC_SMOKE_MANIFEST)

benchmark-smoke-report:
	$(BENCHMARK_SYNTHETIC_SMOKE_CLI) report --manifest ../../$(BENCHMARK_SYNTHETIC_SMOKE_MANIFEST)

benchmark-smoke-clean:
	rm -f $(BENCHMARK_SYNTHETIC_SMOKE_CORPUS)
	rm -f $(BENCHMARK_SYNTHETIC_SMOKE_MANIFEST)

benchmark-stack-prune-containers:
	@$(BENCHMARK_STACK_COMPOSE) down -v --remove-orphans >/dev/null 2>&1 || true
	@docker rm -f $(BENCHMARK_STACK_CONTAINERS) 2>/dev/null || true
	@docker volume rm $(BENCHMARK_STACK_VOLUMES) 2>/dev/null || true

benchmark-stack-up: benchmark-stack-prune-containers
	$(BENCHMARK_STACK_COMPOSE) up --build -d postgres rabbitmq elasticsearch governance-migrate governance-api

benchmark-stack-wait:
	$(BENCHMARK_STACK_CLI) wait

benchmark-stack-reset:
	$(BENCHMARK_STACK_CLI) reset

benchmark-stack-seed:
	$(BENCHMARK_STACK_CLI) seed --reset

benchmark-stack-eval:
	$(BENCHMARK_STACK_CLI) eval --out ../../$(BENCHMARK_STACK_REPORT)

benchmark-stack-report:
	$(BENCHMARK_STACK_CLI) report --file ../../$(BENCHMARK_STACK_REPORT)

benchmark-stack-clean:
	rm -f $(BENCHMARK_STACK_REPORT)
	$(BENCHMARK_STACK_CLI) reset

benchmark-stack-down:
	$(BENCHMARK_STACK_COMPOSE) down -v --remove-orphans
	@docker rm -f $(BENCHMARK_STACK_CONTAINERS) 2>/dev/null || true
	@docker volume rm $(BENCHMARK_STACK_VOLUMES) 2>/dev/null || true

benchmark-stack-run: benchmark-stack-up benchmark-stack-wait benchmark-stack-reset benchmark-stack-seed benchmark-stack-eval benchmark-stack-report

benchmark-agent-live-plan: agent-openrouter-pilot-plan

benchmark-agent-live-check:
	@test -n "$$OPENROUTER_API_KEY" || (echo "OPENROUTER_API_KEY is required for live agent pilot." >&2; exit 1)
	@echo "OPENROUTER_API_KEY is set. Use benchmark-agent-live-validate or benchmark-agent-live-validated-pilot-report only when Governance API is running."

benchmark-agent-live: benchmark-agent-live-check agent-openrouter-pilot-report

benchmark-agent-live-validate: benchmark-agent-live-check agent-openrouter-pilot-validate

benchmark-agent-live-full: benchmark-agent-live-plan benchmark-agent-live benchmark-agent-live-validate

benchmark-agent-live-validated-pilot-plan: agent-openrouter-validated-pilot-plan

benchmark-agent-live-validated-pilot: benchmark-agent-live-check
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-openrouter-validated-pilot $(OPENROUTER_VALIDATED_PILOT_ARGS)

benchmark-agent-live-validated-pilot-report: benchmark-agent-live-check
	mkdir -p examples/agents/openrouter_alias_scout/reports/live-pilot
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-openrouter-validated-pilot-report $(OPENROUTER_VALIDATED_PILOT_REPORT) $(OPENROUTER_VALIDATED_PILOT_ARGS)

benchmark-stack-auth-token:
	@$(BENCHMARK_STACK_AUTH_TOKEN)

benchmark-agent-live-validated-pilot-stack: benchmark-stack-up benchmark-stack-wait benchmark-stack-reset benchmark-stack-seed
	SKEINRANK_AGENT_API_URL="$(BENCHMARK_STACK_API_URL)" SKEINRANK_AGENT_API_TOKEN="$$( $(MAKE) --no-print-directory benchmark-stack-auth-token )" $(MAKE) --no-print-directory benchmark-agent-live-validated-pilot-report

pilot-plan:
	$(PILOT_CLI) plan

pilot-preflight:
	$(PILOT_CLI) preflight

pilot-seed:
	$(PILOT_CLI) seed

pilot-eval:
	$(PILOT_CLI) eval

pilot-report:
	$(PILOT_CLI) report --file "$(PILOT_REPORT_PATH)"

pilot-run:
	$(PILOT_CLI) run

pilot-stack-run: benchmark-stack-up benchmark-stack-wait benchmark-stack-seed
	$(MAKE) --no-print-directory pilot-run PILOT_API_URL="$(BENCHMARK_STACK_API_URL)" PILOT_AUTH_ARGS='--username "$(BENCHMARK_STACK_ADMIN_USERNAME)" --password "$(BENCHMARK_STACK_ADMIN_PASSWORD)"'

agent-openrouter-pilot-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-openrouter-live-pilot-plan

agent-openrouter-pilot:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-openrouter-live-pilot

agent-openrouter-pilot-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/live-pilot
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-openrouter-live-pilot --write-openrouter-live-pilot-report examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-live-pilot-report.json

agent-openrouter-pilot-validate:
	mkdir -p examples/agents/openrouter_alias_scout/reports/live-pilot
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-openrouter-live-pilot --write-openrouter-live-pilot-report examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-live-pilot-validated-report.json --pilot-validate-proposals

agent-openrouter-validated-pilot-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-openrouter-validated-pilot-plan $(OPENROUTER_VALIDATED_PILOT_ARGS)

agent-openrouter-validated-pilot-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/live-pilot
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-openrouter-validated-pilot-report $(OPENROUTER_VALIDATED_PILOT_REPORT) $(OPENROUTER_VALIDATED_PILOT_ARGS)

agent-demo:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report

agent-demo-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-demo-report examples/agents/openrouter_alias_scout/reports/demo-report.json

agent-eval:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-evaluation-report

agent-eval-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-evaluation-report examples/agents/openrouter_alias_scout/reports/evaluation-report.json


agent-deploy-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-deployment-recipe

agent-deploy-recipe:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-deployment-recipe examples/agents/openrouter_alias_scout/reports/deployment-recipe.json

agent-compose-config:
	docker compose --env-file deploy/docker/openrouter-alias-scout.env.example -f deploy/docker/openrouter-alias-scout.compose.yml config

agent-new-alias-smoke-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-new-alias-smoke-plan

agent-new-alias-smoke-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-new-alias-smoke-llm-report examples/agents/openrouter_alias_scout/reports/new-alias-smoke-llm-report.json
agent-es-evidence-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-elasticsearch-evidence-plan

agent-es-evidence-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence-from-elasticsearch > examples/agents/openrouter_alias_scout/reports/elasticsearch-evidence-report.json
agent-tracking-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-agent-tracking-plan

agent-tracking-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-agent-tracking-report examples/agents/openrouter_alias_scout/reports/agent-tracking-report.json


agent-proposal-inbox-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-proposal-inbox-plan

agent-proposal-inbox:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-proposal-inbox examples/agents/openrouter_alias_scout/reports/proposal-inbox.json --llm-review-report examples/agents/openrouter_alias_scout/reports/llm-review-report.json


agent-approved-apply-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-approved-apply-plan

agent-approved-apply:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-approved-apply-plan examples/agents/openrouter_alias_scout/reports/approved-apply-plan.json --proposal-inbox-report examples/agents/openrouter_alias_scout/reports/proposal-inbox.json

agent-snapshot-eval:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-snapshot-evaluation-report examples/agents/openrouter_alias_scout/reports/snapshot-evaluation-report.json --approved-apply-plan examples/agents/openrouter_alias_scout/reports/approved-apply-plan.json

agent-scheduled-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-scheduled-runner-plan

agent-cycle:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-agent-cycle

agent-cycle-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/scheduled
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-agent-cycle-report examples/agents/openrouter_alias_scout/reports/scheduled/agent-cycle-report.json

agent-integration-smoke-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-integration-smoke-plan

agent-integration-smoke-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/integration
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-integration-smoke-report examples/agents/openrouter_alias_scout/reports/integration/full-integration-smoke-report.json


agent-real-es-validation-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-real-elasticsearch-validation-plan

agent-real-es-validation-fixtures:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-real-elasticsearch-validation-fixtures

agent-real-es-validation-index:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --index-real-elasticsearch-validation-docs

agent-real-es-validation-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/real_es_validation
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-real-elasticsearch-validation-report examples/agents/openrouter_alias_scout/reports/real_es_validation/real-es-validation-report.json

agent-artifacts-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-artifacts-standard-plan

agent-artifacts-manifest:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-artifacts-manifest examples/agents/openrouter_alias_scout/reports/scheduled/manifest.json --artifacts-run-id openrouter-alias-scout-cycle


agent-docker-demo-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-docker-demo-plan

agent-docker-demo-config:
	deploy/docker/scripts/openrouter-agent-full-demo.sh config

agent-docker-demo-run:
	deploy/docker/scripts/openrouter-agent-full-demo.sh run

agent-dictionary-quickstart-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-dictionary-quickstart-plan

agent-dictionary-quickstart-payloads:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-dictionary-quickstart-payloads

agent-dictionary-quickstart-validate:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-dictionary-quickstart

agent-runtime-smoke-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-runtime-api-smoke-plan

agent-runtime-smoke-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/runtime-smoke
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-runtime-api-smoke-report examples/agents/openrouter_alias_scout/reports/runtime-smoke/runtime-api-smoke-report.json
