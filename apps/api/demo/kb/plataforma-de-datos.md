# Plataforma de datos (Faro)

Faro recoge los eventos de todos los servicios y los deja listos para el análisis. Lo mantiene el equipo
de Datos. Su nombre viene de que es el punto de referencia para medir el producto.

## Qué hay

- **Carga diaria:** a las 06:00 UTC se carga en el almacén el día anterior completo. El objetivo es que los datos estén listos a las 07:00 UTC.
- **Tablas de tiempo casi real:** las tablas de los paneles se actualizan cada 15 minutos.
- **Convención de nombres:** `dw.<dominio>_<entidad>`, por ejemplo `dw.pedidos_pedido`. Los nombres en inglés se mantienen también en las tablas.

## Reglas

1. **Los datos personales se tokenizan** antes de entrar en Faro. Ninguna tabla de análisis contiene correos ni nombres en claro.
2. **Cada tabla tiene un contrato de datos** en el repositorio `contratos-de-datos`: columnas, tipos, frescura esperada y responsable.
3. **Un cambio en un evento se avisa con antelación** al equipo de Datos. Un evento que cambia sin aviso rompe los paneles.

## Pedir acceso

Escribe en #datos-ayuda con la tabla que necesitas y para qué. El equipo de Datos responde en un día
laborable. El acceso de lectura se concede por rol, no por persona.
