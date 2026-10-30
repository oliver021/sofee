# Estándares de código

Estas reglas son el mínimo común. Cada proyecto puede añadir reglas propias en su README.

## Lenguajes y herramientas

- **Python 3.12** con tipos en las funciones públicas. El formato y el linting los hace ruff; el pipeline falla si no pasa.
- **TypeScript en modo estricto.** No se usa `any` sin un comentario que explique por qué.
- Las pruebas usan pytest o vitest. **Las pruebas no tocan la red**: los proveedores externos se sustituyen por modelos o clientes falsos.

## Nombres y textos

- Los identificadores del código van en inglés.
- Los textos que ve el usuario pasan por el sistema de traducciones. Nunca se escriben en un componente.
- Los comentarios van en el idioma del módulo que los contiene. Explican el porqué, no el qué.

## Errores y logs

- Nunca se captura una excepción sin tratarla o volver a lanzarla con contexto.
- Los logs son estructurados y llevan el identificador de la petición. Ver [observabilidad](observabilidad.md).
- Un secreto nunca aparece en un log, en un mensaje de error ni en una respuesta HTTP.

## Base de datos

- Todo cambio de esquema es una migración versionada. Nada se cambia a mano en producción.
- Las migraciones siguen [ADR-0011](adr-0011-migraciones-sin-caidas.md).

## Secretos

Las claves van en el gestor de secretos del equipo o en variables de entorno. Nunca en el repositorio, ni
siquiera en un fichero de ejemplo con un valor real.
