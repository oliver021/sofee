# Visión general de la arquitectura

La plataforma del equipo se compone de tres servicios de negocio, un punto de entrada común y dos piezas
compartidas. Cada servicio posee sus datos: ningún otro servicio lee sus tablas.

## Piezas

- **Gateway de entrada:** termina TLS, valida la sesión contra Cuentas y reparte las peticiones.
- **Cuentas** (identidad y sesiones): registro, inicio de sesión y roles. Ver [servicio de cuentas](servicio-de-cuentas.md).
- **Pedidos:** crea y sigue los pedidos de los clientes. Tiene su propia base PostgreSQL.
- **Notificaciones:** envía correos y avisos. No decide nada: reacciona a eventos de Pedidos.
- **Bus de eventos:** transporta los eventos entre servicios. La decisión está en [ADR-0007](adr-0007-cola-de-mensajes.md).
- **Faro** (datos): recoge los eventos para análisis. Ver [plataforma de datos](plataforma-de-datos.md).

## Principios

1. **Cada servicio posee sus datos.** Si otro servicio necesita un dato, lo pide por la API o lo recibe en un evento.
2. **Los cambios entre servicios son asíncronos** cuando no hace falta una respuesta inmediata.
3. **Los consumidores son idempotentes.** Un evento puede llegar dos veces; el resultado no cambia.
4. **Lo que se despliega se puede deshacer.** Por eso las migraciones siguen el patrón de [ADR-0011](adr-0011-migraciones-sin-caidas.md).

## Flujo típico de un pedido

1. El cliente envía el pedido a través del gateway.
2. Pedidos guarda el pedido y, en la misma transacción, un evento en su tabla de salida.
3. Un relé publica ese evento en el bus.
4. Notificaciones lo consume y envía el correo de confirmación.
5. Faro lo recoge para el análisis diario.
