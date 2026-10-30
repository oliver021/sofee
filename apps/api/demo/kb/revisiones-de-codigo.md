# Revisiones de código

Todo cambio entra en la rama principal por una revisión. La revisión no es un trámite: es la forma en
la que el equipo aprende del código de los demás.

## Reglas

- Hace falta **una aprobación** del responsable del código que se toca (ver el [mapa del equipo](mapa-del-equipo.md)).
- El pipeline debe estar en verde antes de aprobar. Una revisión no sustituye a las pruebas.
- Un cambio ocupa como máximo unas 400 líneas. Si es más grande, se divide en pasos que se pueden revisar.
- Nadie aprueba su propio cambio. Las erratas en la documentación son la única excepción.
- Quien revisa responde en un día laborable, aunque sea para decir que no puede mirarlo hoy.

## Cómo comentar

Usa un prefijo para que quede claro el peso del comentario:

- **bloqueante:** no se fusiona hasta resolverlo.
- **nit:** detalle menor de estilo. Se puede ignorar sin discutir.
- **pregunta:** quieres entender algo. No implica un cambio.

## Lista de comprobación del revisor

1. ¿Las pruebas cubren el caso que cambia? Las pruebas no usan la red.
2. ¿Hay una migración? Revisa que siga el patrón de [ADR-0011](adr-0011-migraciones-sin-caidas.md).
3. ¿Se registra algún secreto o dato personal en los logs?
4. ¿Hay un cambio de permisos o de autenticación? Pide revisión a Seguridad.
5. ¿El cambio se entiende sin conocer la conversación previa? Si no, falta una descripción.
