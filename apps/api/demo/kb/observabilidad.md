# Observabilidad: logs, métricas y trazas

Un servicio se conoce por lo que se mide. Este documento fija qué medimos y dónde mirarlo.

## Logs

- Son JSON, con los campos `ts`, `level`, `service`, `request_id` y `message`.
- Nunca incluyen secretos, contraseñas ni correos completos. Los correos se truncan.
- Un error lleva el tipo de excepción y el `request_id` para seguir la petición en las trazas.

## Métricas

Las métricas siguen el nombre `<servicio>_<cosa>_<unidad>`. Las más importantes:

- `pedidos_http_request_duration_seconds` (histograma por ruta): base de la latencia de pedidos.
- `pedidos_outbox_lag_seconds`: cuánto tarda un evento en salir de la tabla de salida.
- `notificaciones_sent_total` (contador por resultado).

## Objetivos (SLO)

- **Disponibilidad de la API de pedidos:** 99,5 % al mes, medida como peticiones no fallidas.
- **Latencia de `GET /pedidos/{id}`:** p95 por debajo de 300 ms y p99 por debajo de 800 ms.
- **Retraso del relé de eventos:** p95 por debajo de 30 segundos.

Para medir la latencia antes de optimizar, mira el histograma de la ruta durante una semana completa, no
un momento puntual: los picos de campaña cambian el patrón.

## Trazas

Las trazas siguen la petición a través de los servicios con OpenTelemetry. Se muestrea el 10 % de las
peticiones, y todas las que dan error.

## Alertas

Las alertas críticas van a la guardia. Las de capacidad van a #plataforma. Una alerta sin responsable y sin
runbook se elimina o se corrige en la siguiente revisión.
