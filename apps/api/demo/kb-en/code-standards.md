# Code standards

These rules are the common minimum. Each project may add its own rules in its README.

## Languages and tools

- **Python 3.12** with types on public functions. Formatting and linting are done by ruff; the pipeline fails if it does not pass.
- **TypeScript in strict mode.** `any` is not used without a comment explaining why.
- Tests use pytest or vitest. **Tests do not touch the network**: external providers are replaced by fake models or clients.

## Names and text

- Code identifiers are in English.
- Text the user sees goes through the translation system. It is never written in a component.
- Comments are in the language of the module that contains them. They explain the why, not the what.

## Errors and logs

- An exception is never caught without handling it or re-raising it with context.
- Logs are structured and carry the request identifier. See [observability](observability.md).
- A secret never appears in a log, in an error message or in an HTTP response.

## Database

- Every schema change is a versioned migration. Nothing is changed by hand in production.
- Migrations follow [ADR-0011](adr-0011-zero-downtime-migrations.md).

## Secrets

Keys go in the team's secrets manager or in environment variables. Never in the repository, not even
in an example file with a real value.
