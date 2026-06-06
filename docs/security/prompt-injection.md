# Prompt injection risk taxonomy

SkeinRank treats company language as governed runtime data. That same boundary is
important for AI safety: text coming from users, documents, tickets, web pages,
PDFs, emails, search logs, and evidence snippets is data, not instructions.

Prompt injection happens when untrusted text tries to override the intended
behavior of a model, an agent, or a tool workflow. In SkeinRank, the risk is not
only that a model answers incorrectly. The larger risk is that prompt-like text
is promoted into trusted terminology, evidence, proposals, or runtime context.

## Trust boundary

```text
Trusted control instructions
  -> system prompts, tool policies, RBAC, scoped credentials, human approvals

Untrusted runtime data
  -> user queries, documents, evidence snippets, imported dictionaries,
     search logs, web pages, tickets, email bodies, model outputs
```

Untrusted data can describe instructions, but it must not become an instruction.
A document that says `ignore previous instructions` is evidence text. It is not a
command for the model, the MCP adapter, the Governance API, or an operator.

## Risk categories

| Risk | Example | SkeinRank posture |
| --- | --- | --- |
| Direct prompt injection | A user asks an agent to ignore its instructions or reveal hidden prompts. | Keep system/tool policy separate from user text. Use scoped credentials and proposal-only actions. |
| Indirect prompt injection | A document, PDF, README, wiki page, ticket, or email contains prompt-like instructions. | Treat retrieved/evidence text as untrusted data and surface suspicious snippets as review findings. |
| Tool injection | Untrusted text asks an agent to call email, delete data, publish snapshots, or run deployments. | MCP tools expose safe read/proposal actions only; production mutation requires reviewed workflows. |
| Poisoned terminology | A proposed alias encodes an unsafe instruction, such as mapping a term to a destructive command. | Validate proposals with risk flags before review and snapshot publication. |
| Evidence poisoning | Evidence snippets include commands that look like model instructions or secret-exfiltration requests. | Preserve provenance, show the snippet as evidence, and prevent it from changing tool policy. |
| Context confusion | A model treats runtime context, evidence, or dictionary content as higher-priority instructions. | Assemble prompts with explicit role separation: policy first, untrusted context labeled as data. |

## Prompt-like signals

These phrases are not automatically malicious in every context, but they should
raise risk when they appear inside evidence, aliases, dictionary imports, or
agent-submitted proposals:

```text
ignore previous instructions
reveal the system prompt
show developer message
send credentials
email all documents
delete cluster
run deployment
call this tool
use Gmail
exfiltrate secrets
```

The goal is not to block every occurrence. The goal is to make risky content
visible to reviewers before it becomes trusted terminology or runtime context.

## SkeinRank surfaces

Prompt injection defenses matter most around these SkeinRank surfaces:

- dictionary import and Terminology-as-Code review;
- AI Inbox proposals and evidence snippets;
- Elasticsearch/OpenSearch evidence checks;
- MCP and agent integrations;
- runtime canonicalization and query-plan explanations;
- snapshot publication and rollout workflows.

## Control model

SkeinRank should preserve this control model:

```text
untrusted text
  -> validation and risk findings
  -> proposal review
  -> approved snapshot
  -> binding-scoped runtime use
```

The safe path is proposal-first. Agents may inspect, validate, and submit pending
changes. They should not publish snapshots, mutate bindings, run enrichment jobs,
change production aliases, or operate external tools directly.

## Recommended controls

| Control | Why it matters |
| --- | --- |
| Role separation | User text, document text, evidence, and system/tool policy remain separate. |
| Evidence labels | Retrieved snippets are labeled as untrusted evidence, not instructions. |
| Scoped tool surface | Agents only receive the tools required for the current workflow. |
| Proposal-only writes | Agent output creates reviewable proposals instead of runtime mutations. |
| Human approval | Risky changes require reviewer or admin approval before snapshot publication. |
| Immutable snapshots | Runtime uses pinned approved terminology, not live unreviewed model output. |
| Audit trail | Review decisions, evidence, risk flags, and rollout state remain inspectable. |

## Non-goals

SkeinRank is not a complete prompt-injection firewall for every LLM application.
It does not replace application-level authorization, secret management, output
filtering, data-loss prevention, or vendor-specific model safety controls.

SkeinRank's role is narrower and product-specific: prevent prompt-like, tool-like,
or unsafe text from silently becoming trusted terminology and runtime context for
search, RAG, and agent workflows.

## Related docs

- [`prompt-like-detector.md`](prompt-like-detector.md)
- [`rag-context-boundaries.md`](rag-context-boundaries.md)
- [`agent-tool-safety.md`](agent-tool-safety.md)
- [`../deployment/mcp-integration-kit.md`](../deployment/mcp-integration-kit.md)
- [`../policies/role-boundaries.md`](../policies/role-boundaries.md)
- [`../policies/token-rotation-scoped-agent-credentials.md`](../policies/token-rotation-scoped-agent-credentials.md)
