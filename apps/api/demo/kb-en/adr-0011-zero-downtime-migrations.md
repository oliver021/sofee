# ADR-0011: zero-downtime database migrations

- **Status:** accepted
- **Date:** 2026-01
- **Owners:** Platform and every service team

## Context

A migration that locks a large table for minutes causes an outage. In addition, during a deployment
two versions of the application run side by side, and both must work with the same schema.

## Decision

Every schema change is made in three releases, using the **expand and contract** pattern:

1. **Expand:** add the new thing without removing anything. A new column is optional or has a default value.
2. **Migrate:** the application writes to both places and old data is backfilled in batches.
3. **Contract:** once nothing reads the old thing, it is removed in a later release.

Concrete rules:

- Indexes are created with `CREATE INDEX CONCURRENTLY`, outside a transaction.
- A `NOT NULL` column is first added as nullable, backfilled, and only then constrained.
- Migrations run before the application is deployed, in the release step.
- Each application version must work with the schema of the previous version. That way a rollback is always possible.

## Consequences

- A change that used to be one line is now three releases. It is slower, but there are no downtime windows.
- Code review checks this pattern (see [code reviews](code-reviews.md)).
