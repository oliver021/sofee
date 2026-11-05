# Team glossary

Terms used every day in the team. If one is missing, suggest adding it in #new-hire-questions.

- **ADR (architecture decision record):** a short document that records a decision, its context and its consequences. Example: [ADR-0007](adr-0007-message-queue.md).
- **Canary:** a deployment to a small part of the traffic to check a version before serving it to everyone. See [deployment](deploying-a-service.md).
- **Freeze:** a period in which nothing is deployed except approved exceptions.
- **Expand and contract:** a way to change a schema without downtime: first add the new thing, then migrate, finally remove the old thing.
- **On call:** a shift answering alerts outside normal hours. See [on-call](on-call.md).
- **Idempotent:** said of an operation, that repeating it does not change the result.
- **Outbox:** a table in a service where events are written in the same transaction as the data change.
- **Blameless postmortem:** an analysis of an incident focused on the system and on what is learned, not on who made a mistake.
- **Relay:** the process that reads the outbox table and publishes events to the bus.
- **Owner:** the person or team that decides about a service or a document. They appear in the [team map](team-map.md).
- **Runbook:** written steps to solve a known problem.
- **SEV1 to SEV4:** incident severity levels. See the table in [on-call](on-call.md).
- **SLO (service level objective):** a measurable availability or latency goal. See [observability](observability.md).
- **Faro:** the team's data platform.
