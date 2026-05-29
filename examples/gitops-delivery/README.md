# GitOps delivery examples

These examples accompany `docs/deployment/gitops-delivery-runbook.md`.
They are intentionally conservative and use existing SkeinRank commands only.

## Files

| File | Purpose |
| --- | --- |
| `gitlab-ci.dictionary-delivery.yml` | GitLab CI skeleton for `lint -> plan -> apply -> export -> snapshot-export`. |
| `argocd-runtime-artifact.application.yaml` | ArgoCD Application pointing at a runtime artifact Kustomize path. |
| `flux-gitrepository.yaml` | Flux `GitRepository` source for a runtime artifact repository. |
| `flux-runtime-artifact.kustomization.yaml` | Flux `Kustomization` that reconciles the runtime artifact path. |
| `runtime-artifact/kustomization.yaml` | Kustomize wrapper that creates a ConfigMap from a snapshot artifact. |
| `runtime-artifact/deployment.yaml` | Minimal deployment skeleton mounting the ConfigMap. |
| `runtime-artifact/runtime-snapshot.example.json` | Placeholder example; replace with `skeinrank-migrate snapshot-export` output. |

## Existing SkeinRank commands used

```bash
poetry run skeinrank-migrate lint "$SKEINRANK_DICTIONARY_FILE"
poetry run skeinrank-migrate plan "$SKEINRANK_DICTIONARY_FILE" --output reports/apply-plan.json
poetry run skeinrank-migrate apply "$SKEINRANK_DICTIONARY_FILE" --plan-output reports/applied-plan.json
poetry run skeinrank-migrate export --profile-name "$SKEINRANK_PROFILE_NAME" --output reports/governed-dictionary.json
poetry run skeinrank-migrate snapshot-export --binding-id "$SKEINRANK_BINDING_ID" --source latest --snapshot-version "$SKEINRANK_SNAPSHOT_VERSION" --output runtime/runtime-snapshot.json
```

No example here assumes a SkeinRank-specific deployment controller or reload endpoint.
Use your existing Kubernetes rollout, file-watcher, ArgoCD, or Flux policy to
reload runtime workers after the artifact changes.
