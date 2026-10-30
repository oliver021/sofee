# Servicio de cuentas (identidad y sesiones)

Cuentas gestiona quién es cada usuario, con qué rol entra y cuánto dura su sesión. Lo mantiene el
equipo de Cuentas, y el responsable técnico aparece en el [mapa del equipo](mapa-del-equipo.md).

## Cómo funciona una sesión

- Al iniciar sesión, Cuentas crea una sesión y devuelve un token opaco en una cookie `httpOnly`. El
  token no contiene datos del usuario: solo se resuelve en la base de datos.
- La sesión caduca a los 30 días de inactividad. Cada uso la renueva (caducidad deslizante).
- Un usuario puede revocar todas sus sesiones. Un administrador también puede revocar las de otro usuario, con auditoría.

## Contraseñas y fuerza bruta

- Las contraseñas se guardan con Argon2id. Nunca se guardan en claro ni se registran en los logs.
- Tras 5 intentos fallidos en 15 minutos, el inicio de sesión se bloquea para ese correo y para esa IP
  (respuesta 429 con `Retry-After`).

## Roles

- **regular:** usa la aplicación.
- **admin:** además accede al panel de administración. El último administrador activo no puede desactivarse a sí mismo.

## Para otros servicios

Los servicios no comprueban contraseñas: piden a Cuentas que valide el token de sesión en el gateway y
reciben el usuario y su rol. El inicio de sesión único (SSO) está en estudio y todavía no tiene ADR.

## Accesos de prueba

Para pedir una cuenta de pruebas, escribe en #cuentas-ayuda con tu nombre y el entorno. Nunca compartas
contraseñas por el canal: el equipo de Cuentas las genera y las entrega en privado.
