# Observability: logs, metrics and traces

A service is known by what is measured. This document sets what we measure and where to look at it.

## Logs

- They are JSON, with the fields `ts`, `level`, `service`, `request_id` and `message`.
- They never include secrets, passwords or full email addresses. Email addresses are truncated.
- An error carries the exception type and the `request_id` so the request can be followed in the traces.

## Metrics

Metrics follow the name `<service>_<thing>_<unit>`. The most important ones:

- `orders_http_request_duration_seconds` (histogram per route): the basis for orders latency.
- `orders_outbox_lag_seconds`: how long an event takes to leave the outbox table.
- `notifications_sent_total` (counter per result).

## Objectives (SLOs)

- **Orders API availability:** 99.5% per month, measured as requests that did not fail.
- **Latency of `GET /orders/{id}`:** p95 below 300 ms and p99 below 800 ms.
- **Event relay lag:** p95 below 30 seconds.

To measure latency before optimising, look at the route's histogram over a full week, not at a single
moment: campaign spikes change the pattern.

## Traces

Traces follow the request across services with OpenTelemetry. 10% of requests are sampled, and all
of the ones that fail.

## Alerts

Critical alerts go to on-call. Capacity alerts go to #platform. An alert with no owner and no runbook
is removed or fixed in the next review.
