# Security policy

SkeinRank is a terminology control plane that can sit close to search infrastructure, RAG pipelines, and internal knowledge systems. Please report potential vulnerabilities privately.

## Reporting a vulnerability

If you believe you found a security issue, please do not open a public GitHub issue with exploit details.

Use one of these channels:

- open a private security advisory on GitHub, if available for the repository;
- contact the maintainers through the project organization contact channel;
- if no private channel is available yet, open a minimal public issue that says a private security report is needed, without including exploit details.

Include:

- affected package or component;
- reproduction steps;
- expected impact;
- whether secrets, auth tokens, database state, or runtime snapshots are involved;
- logs with sensitive values redacted.

## Scope

Security-sensitive areas include:

- authentication and service-account tokens;
- scoped agent credentials;
- proposal approval/apply boundaries;
- runtime snapshot publishing;
- support bundle redaction;
- backup/restore artifacts;
- Elasticsearch binding credentials;
- local/company model provider API keys;
- MCP or agent tool access.

## Secrets

Do not include raw secrets in issues or pull requests. SkeinRank docs and tools should prefer redacted diagnostics and read-only smoke reports.

## Supported versions

This repository is currently pre-1.0. Security fixes are expected to land on `main` first unless a release branch is explicitly announced.
