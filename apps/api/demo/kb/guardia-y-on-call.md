# Guardia (on-call)

El equipo de Plataforma y los equipos de servicio cubren la guardia por rotación semanal. El cambio de
turno es los lunes a las 10:00 UTC, y el turno saliente deja una nota con lo abierto.

## Quién responde

- **Primario:** recibe el aviso y es el primero en responder.
- **Secundario:** entra si el primario no confirma en 20 minutos.
- **Responsable de Plataforma:** entra si el secundario tampoco confirma en 40 minutos.

Los avisos llegan por la herramienta de buscapersonas y se confirman con el botón de "reconocer". Sin
confirmación, el aviso sigue escalando.

## Severidades

| Nivel | Qué significa                                                    | Primera respuesta |
| ----- | ---------------------------------------------------------------- | ----------------- |
| SEV1  | Servicio caído para los clientes o pérdida de datos              | 10 minutos        |
| SEV2  | Degradación grave: errores o latencia visibles para muchos       | 30 minutos        |
| SEV3  | Degradación parcial sin impacto grande                           | Siguiente día laborable |
| SEV4  | Incidencia menor o mejora                                        | Sin respuesta inmediata |

## Durante un incidente

1. Confirma el aviso y abre un hilo en #incidentes con el nivel de severidad.
2. Mitiga primero y analiza después. Un rollback suele ser la mejor mitigación.
3. Actualiza el hilo cada 30 minutos aunque no haya novedades.
4. Al cerrar, escribe un postmortem sin culpables en cinco días laborables (ver [el postmortem de marzo](postmortem-caida-de-colas-2026-03.md) como ejemplo).

Quien entra en guardia por primera vez hace dos rotaciones en sombra, acompañando a una persona con experiencia.
