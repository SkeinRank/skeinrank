---
name: Bug report
description: Report a reproducible SkeinRank bug
title: "bug: "
labels: [bug]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for reporting a bug. Please do not include secrets, raw tokens, private documents, or unredacted customer logs.
  - type: textarea
    id: summary
    attributes:
      label: Summary
      description: What happened?
    validations:
      required: true
  - type: textarea
    id: reproduce
    attributes:
      label: Steps to reproduce
      description: Include commands, endpoints, or UI steps.
      placeholder: |
        1. Run ...
        2. Open ...
        3. See ...
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
    validations:
      required: true
  - type: textarea
    id: actual
    attributes:
      label: Actual behavior / logs
      description: Redact secrets before pasting logs.
    validations:
      required: true
  - type: input
    id: version
    attributes:
      label: Version / commit
      placeholder: main@sha or package version
  - type: checkboxes
    id: safety
    attributes:
      label: Safety check
      options:
        - label: I removed secrets, tokens, private documents, and customer data from this report.
          required: true
---
