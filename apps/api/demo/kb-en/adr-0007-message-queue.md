# ADR-0007: message queue for events between services

- **Status:** accepted
- **Date:** 2025-11
- **Owners:** Platform and Orders

## Context

Orders must tell Notifications and Faro about every change, without that notice making the
customer's operation fail. Before, Orders called Notifications synchronously: if Notifications was
slow, the customer waited.

## Options considered

1. **Synchronous call with retries.** Simple, but it couples the availability of the services.
2. **Publish straight to the bus from the operation's code.** Fast, but if the transaction fails after publishing, the event is orphaned.
3. **Outbox table in the same database, with a relay that publishes to the bus.** A bit more work, but the event and the data change are atomic.

## Decision

Option 3 is chosen. Each service writes its events to an outbox table inside the same transaction. A
relay, owned by Platform, reads that table and publishes to the event bus. The bus keeps events for
seven days.

## Consequences

- Delivery is **at least once**: consumers must be idempotent.
- Ordering is only guaranteed within a single aggregate.
- If the bus goes down, events pile up in the outbox table and are published when it comes back. Nothing is lost, but the delay is visible: that is why the relay-lag alert goes to the on-call engineer.
- Time-based retention is not enough: a spike of orders can fill the disk before events expire. See [the March postmortem](postmortem-queue-outage-2026-03.md).
