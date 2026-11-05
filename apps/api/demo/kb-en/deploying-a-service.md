# How a service is deployed

This document describes a change's path from the main branch to production. Service names are in
the [team map](team-map.md) and the architecture is in the [overview](architecture-overview.md).

## Before you start

- The change has an approved review from the code owner (see [code reviews](code-reviews.md)).
- If the change touches the database schema, first follow the [zero-downtime migrations](adr-0011-zero-downtime-migrations.md) pattern.
- Nothing is deployed during the freeze window: Fridays from 16:00 UTC, except fixes approved by the on-call engineer.

## Steps

1. The change is merged into the main branch. That triggers the continuous integration pipeline.
2. The pipeline runs tests, linting and the image build. The image is tagged with the commit hash.
3. Deployment to staging is automatic. Platform sees it on the releases dashboard.
4. Promotion to production is approved by the service owner from the pipeline.
5. The change first reaches a canary with 10% of the traffic for 15 minutes.
6. If the canary's error rate goes above 1%, the deployment stops and goes back to the previous version without intervention.
7. If the canary is healthy, the rest of the traffic moves to the new version.

## When something goes wrong

To undo a deployment, revert the commit in the deployment repository. The pipeline publishes the
previous version again in about five minutes. A database migration is not undone by dropping
columns: that is why the expand and contract pattern exists.

If the incident is serious, open the #incidents channel and follow [on-call](on-call.md).
