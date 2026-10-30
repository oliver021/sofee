# ADR-0007: cola de mensajes para los eventos entre servicios

- **Estado:** aceptada
- **Fecha:** 2025-11
- **Responsables:** Plataforma y Pedidos

## Contexto

Pedidos debe avisar a Notificaciones y a Faro de cada cambio, sin que el aviso haga fallar la operación
del cliente. Antes, Pedidos llamaba a Notificaciones de forma síncrona: si Notificaciones tardaba, el
cliente esperaba.

## Opciones consideradas

1. **Llamada síncrona con reintentos.** Sencilla, pero acopla la disponibilidad de los servicios.
2. **Publicar directamente al bus desde el código de la operación.** Rápido, pero si la transacción falla después de publicar, el evento queda huérfano.
3. **Tabla de salida (outbox) en la misma base de datos, con un relé que publica al bus.** Un poco más de trabajo, pero el evento y el cambio de datos son atómicos.

## Decisión

Se elige la opción 3. Cada servicio escribe sus eventos en una tabla de salida dentro de la misma
transacción. Un relé, propiedad de Plataforma, lee esa tabla y publica en el bus de eventos. El bus
conserva los eventos durante siete días.

## Consecuencias

- Entrega **al menos una vez**: los consumidores deben ser idempotentes.
- El orden se garantiza solo dentro de un mismo agregado.
- Si el bus se cae, los eventos se acumulan en la tabla de salida y se publican al volver. Nada se pierde, pero el retraso es visible: por eso la alerta de retraso del relé va a la guardia.
- La retención por tiempo no basta: un pico de pedidos puede llenar el disco antes de que caduquen los eventos. Ver [el postmortem de marzo](postmortem-caida-de-colas-2026-03.md).
