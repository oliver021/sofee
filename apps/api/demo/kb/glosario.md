# Glosario del equipo

Términos que se usan a diario en el equipo. Si uno falta, propón añadirlo en #preguntas-nuevos.

- **ADR (registro de decisión de arquitectura):** documento corto que recoge una decisión, su contexto y sus consecuencias. Ejemplo: [ADR-0007](adr-0007-cola-de-mensajes.md).
- **Canario:** despliegue a una parte pequeña del tráfico para comprobar una versión antes de servirla a todos. Ver [el despliegue](despliegue-de-un-servicio.md).
- **Congelación:** periodo en el que no se despliega salvo excepciones aprobadas.
- **Expandir y contraer:** forma de cambiar un esquema sin caídas: primero se añade lo nuevo, después se migra, por último se quita lo viejo.
- **Guardia:** turno de respuesta a avisos fuera del horario normal. Ver [guardia](guardia-y-on-call.md).
- **Idempotente:** dicho de una operación, que repetirla no cambia el resultado.
- **Outbox (tabla de salida):** tabla de un servicio donde se escriben los eventos en la misma transacción que el cambio de datos.
- **Postmortem sin culpables:** análisis de un incidente centrado en el sistema y en lo que se aprende, no en quién se equivocó.
- **Relé:** proceso que lee la tabla de salida y publica los eventos en el bus.
- **Responsable (owner):** persona o equipo que decide sobre un servicio o un documento. Aparece en el [mapa del equipo](mapa-del-equipo.md).
- **Runbook:** pasos escritos para resolver un problema conocido.
- **SEV1 a SEV4:** niveles de severidad de un incidente. Ver la tabla en [guardia](guardia-y-on-call.md).
- **SLO (objetivo de nivel de servicio):** meta medible de disponibilidad o latencia. Ver [observabilidad](observabilidad.md).
- **Faro:** la plataforma de datos del equipo.
