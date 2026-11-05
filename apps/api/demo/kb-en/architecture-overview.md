# Architecture overview

The team's platform is made of three business services, a common entry point and two shared pieces.
Each service owns its data: no other service reads its tables.

## Pieces

- **Entry gateway:** terminates TLS, validates the session against Accounts and routes requests.
- **Accounts** (identity and sessions): sign-up, sign-in and roles. See [accounts service](accounts-service.md).
- **Orders:** creates and tracks customer orders. It has its own PostgreSQL database.
- **Notifications:** sends emails and alerts. It decides nothing: it reacts to events from Orders.
- **Event bus:** carries events between services. The decision is in [ADR-0007](adr-0007-message-queue.md).
- **Faro** (data): collects events for analysis. See [data platform](data-platform.md).

## Principles

1. **Each service owns its data.** If another service needs a piece of data, it asks through the API or receives it in an event.
2. **Changes between services are asynchronous** when an immediate answer is not needed.
3. **Consumers are idempotent.** An event may arrive twice; the result does not change.
4. **What is deployed can be undone.** That is why migrations follow the pattern in [ADR-0011](adr-0011-zero-downtime-migrations.md).

## Typical order flow

1. The customer sends the order through the gateway.
2. Orders saves the order and, in the same transaction, an event in its outbox table.
3. A relay publishes that event to the bus.
4. Notifications consumes it and sends the confirmation email.
5. Faro collects it for the daily analysis.
