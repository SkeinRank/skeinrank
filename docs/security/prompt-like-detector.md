# Prompt-like instruction detector

SkeinRank treats dictionary imports, evidence snippets, search logs, user input,
model output, and agent proposals as untrusted data. The prompt-like instruction
detector adds a deterministic review signal for text that looks like it is trying
to override instructions, call tools, reveal secrets, or mutate runtime state.

The detector is intentionally small and explainable. It is not a complete prompt
injection firewall and it does not replace application-level authorization or
secret management. Its product role is to make suspicious untrusted text visible
before it becomes trusted terminology, evidence, or runtime context.

## What it flags

The detector looks for high-signal phrases such as:

```text
ignore previous instructions
reveal the system prompt
send credentials
email all documents
use Gmail
call this tool
delete cluster
publish snapshot immediately
```

Each match is returned as a structured finding with:

- `risk_code`;
- `category`;
- `severity`;
- `path` inside the scanned payload;
- compact `matched_text`;
- reviewer-facing message.

The stable schema is `skeinrank.prompt_injection_risk.v1`.

## Where it runs

The detector is wired into these review surfaces:

| Surface | Behavior |
| --- | --- |
| Dictionary lint | Adds warnings and `risk_findings` for suspicious import text. |
| Console dictionary validate/import | Adds warnings, summary counters, and `risk_findings` to the validation report. |
| Proposal validation | Adds a `prompt_like_instruction` validation check and raises apply-policy risk. |
| Elasticsearch/OpenSearch evidence | Adds evidence response warnings and `risk_findings` when snippets contain prompt-like instructions. |

The detector does not silently delete or rewrite text. It records reviewable risk
metadata so operators can inspect the source and decide whether to reject, edit,
or stop-list the value.

## Dictionary import behavior

When a dictionary contains suspicious text, validation can still complete, but the
report includes warnings and findings:

```json
{
  "status": "valid",
  "summary": {
    "prompt_like_instruction_findings": 1,
    "warnings": 2
  },
  "risk_findings": [
    {
      "risk_code": "prompt_like_instruction",
      "severity": "high",
      "path": "$/terms[0]/aliases[0]",
      "matched_text": "ignore previous instructions"
    }
  ]
}
```

This keeps dry runs and review workflows usable while preventing the finding from
being invisible.

## Proposal behavior

Agent or human proposals that contain prompt-like text receive a
`prompt_like_instruction` validation check. The apply-policy summary treats these
risk flags as high-risk signals, so the proposal cannot be handled as a normal
low-risk batch apply item.

The proposal remains reviewable. The safe path is still:

```text
untrusted proposal text
  -> validation finding
  -> reviewer decision
  -> approved snapshot only if accepted
```

## Evidence behavior

Evidence snippets may legitimately contain malicious or adversarial text. The
right behavior is not to execute or hide it. SkeinRank keeps the snippet as
untrusted evidence and attaches a finding so downstream RAG or agent applications
can keep it outside the instruction boundary.

## Related docs

- [`prompt-injection.md`](prompt-injection.md)
- [`rag-context-boundaries.md`](rag-context-boundaries.md)
- [`agent-tool-safety.md`](agent-tool-safety.md)
- [`../deployment/security.md`](../deployment/security.md)
