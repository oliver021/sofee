# Code reviews

Every change enters the main branch through a review. A review is not a formality: it is how the
team learns from each other's code.

## Rules

- **One approval** is needed from the owner of the code being touched (see the [team map](team-map.md)).
- The pipeline must be green before approving. A review does not replace tests.
- A change is at most about 400 lines. If it is bigger, it is split into steps that can be reviewed.
- Nobody approves their own change. Typos in documentation are the only exception.
- The reviewer answers within one working day, even if only to say they cannot look at it today.

## How to comment

Use a prefix so the weight of the comment is clear:

- **blocking:** it is not merged until this is resolved.
- **nit:** a minor style detail. It can be ignored without discussion.
- **question:** you want to understand something. It does not imply a change.

## Reviewer checklist

1. Do the tests cover the case that changes? Tests do not use the network.
2. Is there a migration? Check that it follows the pattern in [ADR-0011](adr-0011-zero-downtime-migrations.md).
3. Is any secret or personal data written to the logs?
4. Is there a change in permissions or authentication? Ask Security for a review.
5. Can the change be understood without knowing the earlier conversation? If not, a description is missing.
