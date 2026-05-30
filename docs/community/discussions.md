# GitHub Discussions

SkeinRank uses GitHub Discussions for questions, ideas, architecture tradeoffs, integration feedback, and public beta conversations.

Use Issues for reproducible bugs and concrete implementation tasks. Use Discussions when the topic is exploratory, architectural, or a question that does not yet have an actionable fix.

## Recommended categories

| Category | Format | Purpose |
| --- | --- | --- |
| Announcements | Announcement | Maintainer updates, releases, roadmap notes, and public beta announcements. |
| Q&A | Question / Answer | Setup help, runtime API usage, bindings, snapshots, MCP, and integration questions. |
| Ideas | Open-ended discussion | Product suggestions, workflow improvements, and early feature ideas. |
| Architecture / RFC | Open-ended discussion | Runtime routing, governance, enrichment, MCP, Terminology-as-Code, and integration architecture. |
| Integrations | Open-ended discussion | Elasticsearch, OpenSearch, MCP, Claude Desktop, Cursor, LangGraph, RAG, and search backend integrations. |
| Show and tell | Open-ended discussion | Demos, experiments, integrations, screenshots, and real-world usage patterns. |

## Pinned discussion drafts

### Welcome to SkeinRank Discussions

```markdown
Welcome to SkeinRank Discussions 👋

SkeinRank is an open-source Domain Language Control Plane for enterprise search, RAG, and AI-agent workflows.

It helps teams turn noisy internal language — aliases, acronyms, ambiguous terms, and domain-specific jargon — into governed, versioned, binding-aware runtime context.

## What belongs in Discussions

Use Discussions for:

- Questions about how SkeinRank works
- Architecture and runtime design discussions
- Integration ideas for search, RAG, Elasticsearch/OpenSearch, MCP, or agents
- Feedback on the public beta
- Roadmap suggestions
- Use-case examples from real teams

## What belongs in Issues

Use Issues for:

- Reproducible bugs
- Broken commands or failing tests
- Documentation mistakes
- Concrete feature requests with expected behavior
- Regression reports

Thanks for checking out SkeinRank. Questions, ideas, and architecture feedback are welcome.
```

### Public beta feedback: v0.10.0-beta.1

```markdown
This discussion collects feedback for the v0.10.0-beta.1 public beta.

Helpful feedback includes:

- Does the README explain the sidecar/control-plane model quickly enough?
- Did the Docker demo start successfully?
- Which runtime APIs or examples were confusing?
- Are Terminology-as-Code, GitOps, MCP, and enrichment workflows discoverable?
- What should be fixed before a stable v0.10.0 release?

Please open a separate Issue for reproducible bugs or failing commands.
```

### Roadmap: Domain Language Control Plane for Search/RAG/Agents

```markdown
This discussion tracks the high-level SkeinRank roadmap.

Current themes:

- Sidecar architecture and binding-aware runtime APIs
- AI Inbox / human-in-the-loop proposal review
- Terminology-as-Code and GitOps delivery
- Evidence-backed terminology discovery and validation
- MCP integration for Claude Desktop, Cursor, and LangGraph-style agents
- Enrichment safety, blue/green alias swaps, and checkpointing
- Search quality regression checks before terminology rollout

Use this thread for roadmap feedback and category-level direction. Use Issues for scoped implementation tasks.
```

## Issue vs Discussion rule

| Use Issues for | Use Discussions for |
| --- | --- |
| Reproducible bugs | Questions and setup help |
| Failing tests / CI | Architecture tradeoffs |
| Concrete feature requests | Early ideas and RFCs |
| Docs mistakes | Product feedback |
| Regression reports | Integration exploration |

## Maintainer workflow

1. Keep `Announcements` for maintainer-owned posts.
2. Move unclear issues to Discussions when they are questions or RFCs.
3. Link accepted RFCs back to implementation issues.
4. Pin the welcome, public beta feedback, and roadmap discussions while the project is in beta.
5. Keep labels and issue forms aligned with `.github/labels.yml` and `.github/ISSUE_TEMPLATE`.
