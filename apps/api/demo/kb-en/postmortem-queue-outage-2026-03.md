# Postmortem: partial notifications outage caused by the event bus disk (March 2026)

- **Severity:** SEV2
- **Duration:** 47 minutes of degradation
- **Impact:** 12% of order confirmation emails arrived late. No event was lost.
- **Format:** blameless postmortem.

## Summary

The event bus disk filled up because retention was configured by time only (seven days), with no
size limit. A spike of orders from a campaign filled the disk. With a full disk, the bus stopped
accepting new events and the relays kept the events in their outbox table.

## Timeline

- **14:02 UTC:** the order spike begins.
- **14:19 UTC:** the 90% disk alert is sent, but to the Platform channel with no active on-call engineer. Nobody sees it.
- **14:24 UTC:** Notifications starts recording delays. The on-call alert fires because of the relay lag.
- **14:41 UTC:** the on-call engineer acknowledges, opens #incidents and clears the retention of the oldest events.
- **14:49 UTC:** the bus accepts events again. The relays publish what had piled up.

## What we learned

1. An alert that does not reach on-call is not an alert.
2. Time-based retention alone does not protect against a spike. A size limit is needed.
3. The outbox table worked as designed: the delay was visible and nothing was lost (see [ADR-0007](adr-0007-message-queue.md)).

## Actions

- Disk alerts at 70% and 85%, routed to on-call. Owner: Platform.
- A size limit on the bus retention, in addition to the time limit. Owner: Platform.
- A "full bus" runbook with the cleanup steps. Owner: Platform.
- A quarterly drill of a full bus in a test environment. Owner: Platform and Orders.
