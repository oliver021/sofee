# On call

The Platform team and the service teams cover on-call in a weekly rotation. The shift change is on
Mondays at 10:00 UTC, and the outgoing engineer leaves a note with what is still open.

## Who responds

- **Primary:** receives the alert and is the first to respond.
- **Secondary:** steps in if the primary does not acknowledge within 20 minutes.
- **Platform lead:** steps in if the secondary does not acknowledge within 40 minutes.

Alerts arrive through the paging tool and are acknowledged with the "acknowledge" button. Without
acknowledgement, the alert keeps escalating.

## Severities

| Level | What it means                                                  | First response       |
| ----- | -------------------------------------------------------------- | -------------------- |
| SEV1  | Service down for customers, or data loss                       | 10 minutes           |
| SEV2  | Serious degradation: errors or latency visible to many users   | 30 minutes           |
| SEV3  | Partial degradation without major impact                       | Next working day     |
| SEV4  | Minor issue or improvement                                     | No immediate response |

## During an incident

1. Acknowledge the alert and open a thread in #incidents with the severity level.
2. Mitigate first and analyse later. A rollback is usually the best mitigation.
3. Update the thread every 30 minutes even if there is no news.
4. When you close it, write a blameless postmortem within five working days (see [the March postmortem](postmortem-queue-outage-2026-03.md) as an example).

Whoever goes on call for the first time does two rotations in shadow, accompanying an experienced person.
