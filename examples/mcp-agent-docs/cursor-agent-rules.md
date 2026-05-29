# Cursor agent rules for SkeinRank MCP

Use SkeinRank MCP as a developer integration assistant, not as a runtime admin.

Allowed tools:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

Allowed:

- inspect bindings before editing integration code;
- explain sample queries with the binding used by the current route;
- validate alias candidates found in tests, docs, logs, or code comments;
- submit pending proposals with clear evidence;
- update code/docs/tests to pass `binding_id` correctly.

Not allowed:

- invent profile names or binding ids;
- claim a proposal changed production runtime;
- approve suggestions;
- apply dictionaries;
- publish snapshots;
- add calls to non-existent runtime reload endpoints.

Preferred workflow:

```text
read code -> list bindings -> explain query -> validate alias -> submit proposal -> update docs/tests
```
