# Postmortem: caída parcial de notificaciones por el disco del bus de eventos (marzo 2026)

- **Severidad:** SEV2
- **Duración:** 47 minutos de degradación
- **Impacto:** el 12 % de los correos de confirmación de pedidos llegaron con retraso. No se perdió ningún evento.
- **Formato:** postmortem sin culpables.

## Resumen

El disco del bus de eventos se llenó porque la retención estaba configurada solo por tiempo (siete días),
sin límite de tamaño. Un pico de pedidos por una campaña llenó el disco. Con el disco lleno, el bus dejó
de aceptar eventos nuevos y los relés se quedaron con los eventos en su tabla de salida.

## Cronología

- **14:02 UTC:** empieza el pico de pedidos.
- **14:19 UTC:** la alerta de disco al 90 % se envía, pero al canal de Plataforma sin guardia activa. Nadie la ve.
- **14:24 UTC:** Notificaciones empieza a registrar retrasos. El aviso de la guardia salta por el retraso del relé.
- **14:41 UTC:** la guardia confirma, abre #incidentes y limpia la retención de los eventos más antiguos.
- **14:49 UTC:** el bus vuelve a aceptar eventos. Los relés publican lo acumulado.

## Qué aprendimos

1. Una alerta que no llega a la guardia no es una alerta.
2. La retención por tiempo sola no protege de un pico. Hace falta un límite de tamaño.
3. La tabla de salida funcionó como se diseñó: el retraso fue visible y no hubo pérdidas (ver [ADR-0007](adr-0007-cola-de-mensajes.md)).

## Acciones

- Alertas de disco al 70 % y al 85 %, enrutadas a la guardia. Responsable: Plataforma.
- Límite de tamaño en la retención del bus, además del límite de tiempo. Responsable: Plataforma.
- Runbook de "bus lleno" con los pasos de limpieza. Responsable: Plataforma.
- Simulacro trimestral de un bus lleno en un entorno de pruebas. Responsable: Plataforma y Pedidos.
