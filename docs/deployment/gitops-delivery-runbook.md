# GitOps delivery runbook for Terminology-as-Code

This runbook describes how to deliver reviewed SkeinRank terminology changes through standard GitOps tooling. SkeinRank validates and manages terminology state. GitLab CI, Jenkins, ArgoCD, Flux, or another delivery system moves reviewed runtime artifacts to serving workloads.

The boundary is intentionally explicit:

```text
SkeinRank control plane -> validates, applies, exports, snapshots
GitOps delivery plane   -> commits, syncs, mounts, reloads, rolls back
Runtime/data plane      -> loads immutable snapshot artifacts and serves search/RAG
```

SkeinRank should not pretend to be the CI/CD system. It produces governed artifacts. Your existing delivery tooling decides how those artifacts reach the serving environment.

## Recommended repositories

Use two Git repositories or two clearly separated paths in one repository:

| Repository/path | Contents | Owner | Purpose |
| --- | --- | --- | --- |
| terminology source | `*.dictionary.yaml` or `*.dictionary.json`, plan reports | domain owners, agents, reviewers | Human-reviewable input and CI evidence. |
| runtime delivery | `runtime-snapshot.json` or a Kubernetes ConfigMap/Kustomize wrapper | platform/SRE | Immutable artifact consumed by headless workers. |

This split avoids making runtime pods depend on PostgreSQL. PostgreSQL remains the control-plane source of truth, while runtime workers consume a small binding-scoped artifact.

## End-to-end flow

```text
1. Human or agent opens a pull request with a dictionary change.
2. CI runs skeinrank-migrate lint locally.
3. CI runs skeinrank-migrate plan against the Governance API.
4. Reviewers inspect the dictionary diff and the plan artifact.
5. A protected branch job runs skeinrank-migrate apply --plan-output.
6. CI exports the governed dictionary back to JSON for audit.
7. CI exports a binding-scoped runtime snapshot artifact.
8. GitLab CI, ArgoCD, or Flux delivers that artifact to runtime workers.
9. Runtime workers reload the mounted file or are restarted by the platform.
10. Rollback is a Git revert of the delivered artifact commit.
```

The only SkeinRank write step in this runbook is `skeinrank-migrate apply`. `snapshot-export` writes a binding-scoped artifact for runtime delivery rather than mutating search infrastructure. `lint`, `plan`, `export`, `snapshot-export`, `snapshot-inspect`, and `snapshot-eval` are read-only or local artifact operations.

## Required CI variables

The examples use environment variables instead of hard-coded URLs or tokens:

| Variable | Example | Notes |
| --- | --- | --- |
| `SKEINRANK_CONSOLE_API_URL` | `https://skeinrank.internal` | Used by `skeinrank-migrate --api-url` defaults. |
| `SKEINRANK_API_TOKEN` | masked secret | Used automatically by `skeinrank-migrate` when `--token` is omitted. |
| `SKEINRANK_DICTIONARY_FILE` | `examples/terminology-as-code/platform_ops.dictionary.yaml` | Dictionary source file in Git. |
| `SKEINRANK_PROFILE_NAME` | `platform_ops` | Profile to export after apply. |
| `SKEINRANK_BINDING_ID` | `1` | Binding used for runtime artifact export. |
| `SKEINRANK_SNAPSHOT_VERSION` | `platform_ops@${CI_COMMIT_SHORT_SHA}` | Optional version label for source=`latest` export. |

`SKEINRANK_API_TOKEN` should be a scoped service token with the smallest role needed for the pipeline. Keep read-only jobs separate from the protected apply job when your CI system supports it.

## GitLab CI shape

The sample file [`examples/gitops-delivery/gitlab-ci.dictionary-delivery.yml`](../../examples/gitops-delivery/gitlab-ci.dictionary-delivery.yml) shows the conservative pipeline:

```text
lint -> plan -> apply -> export -> snapshot_export -> optional delivery commit
```

The jobs call the existing CLI only:

```bash
poetry run skeinrank-migrate lint "$SKEINRANK_DICTIONARY_FILE"
poetry run skeinrank-migrate plan "$SKEINRANK_DICTIONARY_FILE" --output reports/apply-plan.json
poetry run skeinrank-migrate apply "$SKEINRANK_DICTIONARY_FILE" --plan-output reports/applied-plan.json
poetry run skeinrank-migrate export --profile-name "$SKEINRANK_PROFILE_NAME" --output reports/governed-dictionary.json
poetry run skeinrank-migrate snapshot-export --binding-id "$SKEINRANK_BINDING_ID" --source latest --snapshot-version "$SKEINRANK_SNAPSHOT_VERSION" --output runtime/runtime-snapshot.json
poetry run skeinrank-migrate snapshot-inspect runtime/runtime-snapshot.json --output runtime/runtime-snapshot.summary.json
```

For production, keep `apply` and delivery jobs restricted to protected branches or manual approvals. Pull requests should run `lint` and `plan` and archive the plan report for review.

## ArgoCD delivery shape

ArgoCD should watch the runtime delivery repository, not the mutable PostgreSQL-backed control-plane database. A common pattern is:

```text
runtime delivery repo
  runtime-snapshot.json
  kustomization.yaml
  deployment.yaml
```

The example [`examples/gitops-delivery/argocd-runtime-artifact.application.yaml`](../../examples/gitops-delivery/argocd-runtime-artifact.application.yaml) points ArgoCD at [`examples/gitops-delivery/runtime-artifact`](../../examples/gitops-delivery/runtime-artifact). That Kustomize path creates a ConfigMap from the snapshot file and mounts it into a runtime worker container.

The runtime worker should then use one of your existing application patterns:

- watch the mounted file and reload its in-memory matcher when the file changes;
- or let Kubernetes roll/restart the worker deployment after the ConfigMap changes.

SkeinRank does not need a project-specific reload endpoint for this runbook.

## Flux delivery shape

Flux uses the same runtime artifact repository idea. The examples [`examples/gitops-delivery/flux-gitrepository.yaml`](../../examples/gitops-delivery/flux-gitrepository.yaml) and [`examples/gitops-delivery/flux-runtime-artifact.kustomization.yaml`](../../examples/gitops-delivery/flux-runtime-artifact.kustomization.yaml) show a `GitRepository` source and a `Kustomization` that reconciles the same runtime artifact path.

Flux and ArgoCD are pull-based: the cluster watches Git and applies what it sees. GitLab CI is often still useful before that point because it validates, applies, and exports the SkeinRank artifacts.

## Rollback

Rollback should be operationally boring:

```text
git revert <runtime-artifact-commit>
ArgoCD/Flux reconciles the previous ConfigMap
runtime worker reloads the previous snapshot artifact
```

For push-style GitLab CI delivery, the rollback job should copy or mount the previous artifact in the same way the forward deployment did. Avoid ad-hoc manual changes in the runtime pod; keep the runtime artifact in Git so the audit trail remains clear.

## Preflight checklist

Before enabling automatic delivery:

- `skeinrank-migrate lint` passes locally.
- `skeinrank-migrate plan` is archived and reviewed.
- `apply` runs only on protected branches or after approval.
- `snapshot-export` writes a binding-scoped artifact, not a global dictionary.
- runtime workers can load the artifact without direct PostgreSQL access.
- rollback is a Git revert, not a database edit.
- service tokens are scoped and stored as masked CI variables.

## Non-goals

This runbook does not introduce new REST endpoints, worker reload hooks, Terraform providers, Helm charts, or provider-specific deployment controllers. It documents how to use the existing `skeinrank-migrate` commands with standard GitOps tools. Heavier packaging layers can be added without changing the Terminology-as-Code contract.
