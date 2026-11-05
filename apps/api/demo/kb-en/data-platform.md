# Data platform (Faro)

Faro collects the events of every service and leaves them ready for analysis. The Data team maintains
it. Its name comes from being the reference point for measuring the product.

## What there is

- **Daily load:** at 06:00 UTC the whole previous day is loaded into the warehouse. The goal is for the data to be ready by 07:00 UTC.
- **Near-real-time tables:** the dashboard tables are refreshed every 15 minutes.
- **Naming convention:** `dw.<domain>_<entity>`, for example `dw.orders_order`.

## Rules

1. **Personal data is tokenised** before entering Faro. No analysis table contains emails or names in the clear.
2. **Every table has a data contract** in the `data-contracts` repository: columns, types, expected freshness and owner.
3. **A change to an event is announced in advance** to the Data team. An event that changes without notice breaks the dashboards.

## Asking for access

Write in #data-help with the table you need and what for. The Data team answers within one working
day. Read access is granted by role, not by person.
