# First company pilot checklist

Use this checklist together with `docs/pilots/first-company-pilot-runbook.md`.
Keep completed company copies out of public commits.

## Intake

```text
Pilot owner:
Reviewer:
Index or alias:
Text fields:
Target field:
Optional filter field/value:
Initial profile name:
Initial canonical terms:
Initial aliases:
Evidence checks:
Runtime queries:
```

## Before the company run

- [ ] `make benchmark-retrieval-eval` passed locally.
- [ ] `make benchmark-smoke-generate` produced a 5k manifest locally.
- [ ] `make benchmark-performance-report` produced an offline performance report.
- [ ] Company config was copied to `/tmp/skeinrank-company-pilot.json` or another ignored/private path.
- [ ] No real credentials were committed.
- [ ] Pilot binding mode is `dry_run`.

## Company pilot flow

- [ ] `make pilot-plan PILOT_CONFIG=/tmp/skeinrank-company-pilot.json` reviewed.
- [ ] `make pilot-preflight PILOT_CONFIG=/tmp/skeinrank-company-pilot.json` passed.
- [ ] `make pilot-seed PILOT_CONFIG=/tmp/skeinrank-company-pilot.json` completed.
- [ ] `make pilot-eval PILOT_CONFIG=/tmp/skeinrank-company-pilot.json` completed.
- [ ] `make pilot-report PILOT_CONFIG=/tmp/skeinrank-company-pilot.json` reviewed.

## Safety review

- [ ] OpenRouter calls were disabled unless explicitly testing the validated pilot.
- [ ] Proposal submission was disabled.
- [ ] Approve/apply was disabled.
- [ ] Snapshot publishing was disabled.
- [ ] Elasticsearch writes were disabled.
- [ ] Runtime mutation after seed was disabled.

## Exit decision

```text
Pilot status: passed / needs tuning / blocked
Main failed checks:
Dictionary changes needed:
Binding/index changes needed:
Evidence examples worth showing:
Runtime query examples worth showing:
Next action:
```


## Troubleshooting bundle

- [ ] If the pilot needs support review, run `make support-bundle-export`.
- [ ] Inspect the bundle with `make support-bundle-inspect`.
- [ ] Keep the generated ZIP out of public commits.
- [ ] Share the ZIP only through the approved private channel.
