# ADR-0011: migraciones de base de datos sin caídas

- **Estado:** aceptada
- **Fecha:** 2026-01
- **Responsables:** Plataforma y todos los equipos de servicio

## Contexto

Una migración que bloquea una tabla grande durante minutos produce una caída. Además, durante un
despliegue conviven dos versiones de la aplicación, y las dos deben funcionar con el mismo esquema.

## Decisión

Cada cambio de esquema se hace en tres releases, con el patrón **expandir y contraer**:

1. **Expandir:** se añade lo nuevo sin quitar nada. Una columna nueva es opcional o tiene un valor por defecto.
2. **Migrar:** la aplicación escribe en ambos sitios y se rellenan los datos viejos en lotes.
3. **Contraer:** cuando nada lee lo viejo, se quita en una release posterior.

Reglas concretas:

- Los índices se crean con `CREATE INDEX CONCURRENTLY`, fuera de una transacción.
- Una columna `NOT NULL` se añade primero como nullable, se rellena y después se restringe.
- Las migraciones se ejecutan antes del despliegue de la aplicación, en el paso de release.
- Cada versión de la aplicación debe funcionar con el esquema de la versión anterior. Así el rollback siempre es posible.

## Consecuencias

- Un cambio que antes era una línea ahora son tres releases. Es más lento, pero no hay ventanas de caída.
- La revisión de código comprueba este patrón (ver [revisiones de código](revisiones-de-codigo.md)).
