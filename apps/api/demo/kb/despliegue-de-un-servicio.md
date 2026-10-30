# Cómo se despliega un servicio

Este documento describe el camino de un cambio desde la rama principal hasta producción. Los nombres
de los servicios están en el [mapa del equipo](mapa-del-equipo.md) y la arquitectura en la
[visión general](arquitectura-general.md).

## Antes de empezar

- El cambio tiene una revisión aprobada por el responsable del código (ver [revisiones de código](revisiones-de-codigo.md)).
- Si el cambio toca el esquema de la base de datos, sigue primero el patrón de [migraciones sin caídas](adr-0011-migraciones-sin-caidas.md).
- No se despliega en la ventana de congelación: los viernes desde las 16:00 UTC, salvo correcciones aprobadas por la guardia.

## Pasos

1. Se fusiona el cambio en la rama principal. Eso dispara el pipeline de integración continua.
2. El pipeline ejecuta pruebas, linting y la compilación de la imagen. La imagen se etiqueta con el hash del commit.
3. El despliegue en pruebas es automático. Plataforma lo ve en el panel de versiones.
4. La promoción a producción la aprueba el responsable del servicio desde el pipeline.
5. El cambio llega primero a un canario con el 10 % del tráfico durante 15 minutos.
6. Si la tasa de errores del canario supera el 1 %, el despliegue se detiene y vuelve a la versión anterior sin intervención.
7. Si el canario está sano, el resto del tráfico pasa a la nueva versión.

## Cuando algo sale mal

Para deshacer un despliegue, se revierte el commit en el repositorio de despliegue. El pipeline vuelve a
publicar la versión anterior en unos cinco minutos. Una migración de base de datos no se deshace
borrando columnas: por eso existe el patrón expandir y contraer.

Si el incidente es grave, abre el canal #incidentes y sigue la [guardia](guardia-y-on-call.md).
