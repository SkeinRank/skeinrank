---
name: Feature request
description: Suggest a product, API, integration, or docs improvement
title: "feat: "
labels: [enhancement]
body:
  - type: textarea
    id: problem
    attributes:
      label: Problem
      description: What user or operator problem should this solve?
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: Proposed solution
      description: Describe the desired behavior.
    validations:
      required: true
  - type: dropdown
    id: area
    attributes:
      label: Area
      options:
        - Core SDK / CLI
        - Governance API
        - UI Control Plane
        - Agent / MCP tools
        - Enrichment / Elasticsearch
        - GitOps / Terminology-as-Code
        - Docs / demo
        - Other
    validations:
      required: true
  - type: textarea
    id: safety
    attributes:
      label: Safety considerations
      description: Does this introduce direct mutation, credentials, external calls, or runtime rollout risk?
  - type: checkboxes
    id: contract
    attributes:
      label: Contribution fit
      options:
        - label: This request preserves the governed proposal/review/snapshot workflow or explicitly explains why it should change.
          required: true
---
