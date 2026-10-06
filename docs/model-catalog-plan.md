# Plan: catálogo de modelos inter-provider

Hoy `apps/web` pide `GET /providers/models` y pinta, sin filtrar, cada modelo
habilitado de cada provider habilitado — id crudo incluido (`meta-llama/Meta-Llama-3.1-8B-Instruct`)
y el nombre interno del provider. Con un solo NVIDIA NIM ya son 82 filas. Ese
endpoint es correcto como _inventario técnico_ (y se reutiliza más abajo), pero
está mal como _menú para un usuario regular_.

Este documento diseña la capa que falta: un **catálogo curado**, editable desde
el panel de admin, que el usuario regular sí ve — desacoplado de qué provider
sirve cada modelo por debajo.

## 1. La idea central: binding, no espejo

Una entrada de catálogo (`ModelCatalogEntry`) es lo que el usuario ve: un
nombre, una descripción, una categoría. No apunta a **un** modelo — apunta a
una **lista ordenada** de `(provider, modelo)` candidatos (`ModelCatalogBinding`),
cada uno con una prioridad. El primero disponible gana.

```
"Rápido" (catalog entry)
  ├─ prioridad 0: DeepInfra · meta-llama/Meta-Llama-3.1-8B-Instruct
  └─ prioridad 1: NVIDIA NIM · meta/llama-3.1-8b-instruct   (fallback)
```

Esto compra dos cosas a la vez:

- **Desacople**: el admin puede tener tres providers exponiendo variantes del
  "mismo" modelo y el usuario elige uno solo, con un nombre que no depende de
  ninguno de los tres.
- **Resiliencia barata**: si el binding primario queda inhabilitado (el admin
  apaga el provider, rota mal una credencial, el modelo se da de baja en el
  proveedor), la entrada sigue "disponible" mientras quede un fallback vivo —
  sin que el usuario note nada.

No se modela como _load balancing_ (no hay pesos ni round-robin): es
simplemente "probá el primero; si no sirve, el siguiente". Añadir distribución
de carga real es una extensión futura sobre la misma tabla (ya tiene el orden),
no un rediseño.

## 2. Modelo de datos

### `model_catalog_entries`

| Campo                      | Tipo                        | Notas                                                                                        |
| -------------------------- | --------------------------- | -------------------------------------------------------------------------------------------- |
| `id`                       | UUID pk                     |                                                                                              |
| `slug`                     | text, unique                | id estable para el cliente (`fast`, `balanced`); no cambia aunque se edite el nombre         |
| `display_name`             | text                        | lo que ve el usuario                                                                         |
| `description`              | text nullable               | una línea, opcional                                                                          |
| `category`                 | text                        | agrupación suelta para el selector (`general`, `rapido`, `razonamiento`, `vision`, `codigo`) |
| `is_enabled`               | bool                        | el admin puede tener una entrada en preparación sin publicarla                               |
| `sort_order`               | int                         | orden manual en el selector del usuario                                                      |
| `created_by`               | UUID fk → `users`, nullable |                                                                                              |
| `created_at`, `updated_at` | timestamptz                 |                                                                                              |

`category` es texto libre, no un enum de base de datos: es una etiqueta de UI
(qué ícono/grupo mostrar), no una regla de negocio — si mañana se agrega una
categoría no hace falta una migración. Si en el futuro empieza a condicionar
lógica real (permisos por categoría, p. ej.), ese es el momento de promoverla
a enum.

### `model_catalog_bindings`

| Campo               | Tipo                                        | Notas                                                                  |
| ------------------- | ------------------------------------------- | ---------------------------------------------------------------------- |
| `id`                | UUID pk                                     |                                                                        |
| `catalog_entry_id`  | UUID fk → `model_catalog_entries` (CASCADE) |                                                                        |
| `provider_model_id` | UUID fk → `provider_models` (CASCADE)       | reutiliza la fila que ya sincroniza el admin de providers              |
| `priority`          | int                                         | 0 = primario; más alto = fallback más lejano                           |
| `is_enabled`        | bool                                        | pausar un binding sin borrarlo (p. ej. mientras se investiga un fallo) |
| `created_at`        | timestamptz                                 |                                                                        |

`UNIQUE(catalog_entry_id, provider_model_id)` — un modelo no se ata dos veces
a la misma entrada. Nada impide que el _mismo_ `provider_model` esté atado a
_varias_ entradas de catálogo (un modelo potente puede ser el fallback de
"Rápido" y el primario de "Potente" a la vez).

## 3. Resolución de disponibilidad

Un binding cuenta como usable si, en cadena: `binding.is_enabled` →
`provider_model.is_enabled` → `provider.is_enabled` → el provider tiene una
credencial activa. La entrada de catálogo está "disponible" si al menos un
binding lo es, ordenado por `priority`. Esta función vive en
`app/services/catalog.py` y es la que:

- calcula el flag `is_available` que ve el usuario en `GET /catalog`;
- más adelante (fuera de este plan — hoy `conversations.py` no enruta a un
  provider real todavía) sería el punto donde se resuelve "qué provider/modelo
  concreto uso para esta conversación", con el mismo orden de prioridad
  sirviendo de failover automático.

## 4. API

**Admin** (`/admin/catalog`, `require_admin`, mismo patrón que
`providers_admin.py`: CSRF en toda mutación, auditoría en cada una):

```
GET    /admin/catalog                         lista entradas + sus bindings
POST   /admin/catalog                         crear entrada
PATCH  /admin/catalog/{id}                    editar entrada
DELETE /admin/catalog/{id}                    borrar entrada (cascada a bindings)
POST   /admin/catalog/{id}/bindings           agregar binding {provider_model_id, priority?}
PATCH  /admin/catalog/{id}/bindings/{bid}     {priority?, is_enabled?} — reordenar/pausar
DELETE /admin/catalog/{id}/bindings/{bid}     quitar binding
```

El picker de "qué modelo atar" reutiliza el endpoint que ya existe,
`GET /providers/models` — ahí sí tiene sentido como fuente: es el admin
construyendo el catálogo a partir del inventario real, no un usuario regular
viendo el inventario.

**Usuario regular** (`/catalog`, `require_user`):

```
GET /catalog   →  [{ id, slug, display_name, description, category, is_available }]
```

Sin `provider_id`, sin `model_id`, sin nombre de provider. Es el reemplazo
directo de lo que hoy consume `apps/web/src/lib/models.svelte.ts` desde
`/providers/models`.

## 5. UX — panel de admin

Nueva vista **Catálogo**, junto a Proveedores/Usuarios/Auditoría:

- Tabla: nombre, categoría, estado, cantidad de bindings, disponibilidad
  calculada (mismo criterio que ve el usuario, para que el admin nunca tenga
  que adivinar "¿esto se ve o no se ve?").
- Drawer de alta/edición de la entrada (nombre, slug, descripción, categoría,
  activo, orden) — mismo patrón visual que `ProviderForm.svelte`.
- Dentro del drawer, en modo edición, una sección de bindings (espejo de
  `ModelsSection.svelte`): lista ordenada con badge "Primario" / "Fallback #N",
  botones subir/bajar, un switch por binding y un selector para agregar uno
  nuevo — alimentado por `/providers/models`, filtrando los ya atados.

## 6. UX — `apps/web`

`models.svelte.ts` cambia su única llamada de `/providers/models` a
`/catalog`. El contrato de `ModelOption` que ya consume el selector
(`id`, `label`, `provider`) se simplifica: `id` pasa a ser el `slug` (estable,
no un compuesto `provider_id:model_id` que cambiaba si el admin rotaba el
binding), y el campo `provider` desaparece del tipo — no hay identidad de
provider que mostrarle al usuario. Una entrada sin ningún binding disponible
se filtra o se muestra deshabilitada con un tooltip, nunca oculta en silencio
sin explicación.

## 7. Fases

1. Modelo de datos + migración (`model_catalog_entries`, `model_catalog_bindings`).
2. Servicio de resolución de disponibilidad + endpoints admin (CRUD entradas y bindings, con auditoría).
3. Endpoint público `GET /catalog`.
4. Vista **Catálogo** en `apps/admin`.
5. `apps/web`: `models.svelte.ts` migra de `/providers/models` a `/catalog`.
6. Seed de desarrollo: una entrada de ejemplo con bindings sobre los providers ya sembrados, para que el catálogo no arranque vacío en `seed-dev`.

## 8. Fuera de alcance (explícito)

- Enrutar de verdad una conversación a un binding concreto (`conversations.py`
  no llama a ningún provider todavía — eso es un plan aparte).
- Distribución de carga / costos por uso entre bindings del mismo nivel de
  prioridad.
- Permisos por categoría o por usuario (todo usuario regular ve el mismo
  catálogo).
