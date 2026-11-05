/**
 * Spanish copy for the backend messages the admin panel can show. The API answers `detail` in
 * English (it also serves tests and clients); the admin is Spanish-only, so it translates the
 * ones it knows and shows anything else as it came.
 */

const EXACT: Readonly<Record<string, string>> = {
  'Invalid credentials': 'El correo o la contraseña no son correctos.',
  'Too many login attempts. Try again later.': 'Demasiados intentos. Espera un momento e inténtalo de nuevo.',
  'Too many attempts. Try again later.': 'Demasiados intentos. Espera un momento e inténtalo de nuevo.',
  'Not authenticated': 'Sesión no válida',
  'Admin only': 'Esta acción es solo para administradores.',
  'Account disabled': 'La cuenta está desactivada.',
  'Invalid CSRF token': 'La sesión caducó. Recarga la página e inténtalo de nuevo.',
  'User not found': 'No se encontró el usuario.',
  'Session not found': 'No se encontró la sesión.',
  'Provider not found': 'No se encontró el proveedor.',
  'Provider model not found': 'No se encontró el modelo del proveedor.',
  'Provider name already exists': 'Ya existe un proveedor con ese nombre.',
  'Model not found': 'No se encontró el modelo.',
  'Model already bound to this entry': 'Ese modelo ya está en esta entrada del catálogo.',
  'Binding not found': 'No se encontró esa asignación de modelo.',
  'Entry not found': 'No se encontró la entrada del catálogo.',
  'Slug already exists': 'Ya existe una entrada con ese identificador.',
  'Title is blank': 'El título no puede estar vacío.',
  'Document not found': 'No se encontró el documento.',
  'Run not found': 'No se encontró la ejecución.',
  'Feedback not found': 'No se encontró la valoración.',
  'Unknown agent mode': 'Ese modo del asistente no existe.',
  'Profile version not found': 'No se encontró esa versión del perfil.',
  'Profile version conflict, retry':
    'Otra persona guardó una versión nueva. Recarga el perfil e inténtalo de nuevo.',
  'Invalid cursor': 'La paginación ya no es válida. Recarga la lista.',
  'You cannot change your own role': 'No puedes cambiar tu propio rol.',
  'You cannot deactivate your own account': 'No puedes desactivar tu propia cuenta.',
  'You cannot revoke your own current session': 'No puedes cerrar tu sesión actual desde aquí.',
  'Empty model list returned by provider': 'El proveedor no devolvió ningún modelo.',
  'base_url is required for this provider': 'Este proveedor necesita una URL base.',
  'base_url is required for openai_compatible providers':
    'Un proveedor compatible con OpenAI necesita una URL base.',
};

/** What the browser says when `fetch` never got an answer, in each engine. */
const NETWORK_FAILURES = ['Failed to fetch', 'Load failed', 'NetworkError when attempting to fetch resource.'];

const PATTERNS: ReadonlyArray<readonly [RegExp, (match: RegExpMatchArray) => string]> = [
  [
    /^List models failed with HTTP (401|403)$/,
    ([, status]) =>
      `El proveedor rechazó la clave (HTTP ${status}). Revisa la clave y la URL del proveedor.`,
  ],
  [
    /^List models failed with HTTP (\d+)$/,
    ([, status]) => `El proveedor respondió con HTTP ${status} al listar los modelos.`,
  ],
  [
    /^Chat completion failed with HTTP (\d+)$/,
    ([, status]) => `El proveedor respondió con HTTP ${status} al probar el modelo.`,
  ],
  [/^Network error: .+$/, () => 'No se pudo conectar con el proveedor. Revisa la URL y la red.'],
  [/^String should have at least (\d+) characters?$/, ([, n]) => `debe tener al menos ${n} caracteres`],
  [/^String should have at most (\d+) characters?$/, ([, n]) => `debe tener como máximo ${n} caracteres`],
  [/^Field required$/, () => 'es obligatorio'],
  [/^(?:value is not a valid email address|Value error, value is not a valid email address).*/, () => 'no es un correo válido'],
];

/** The Spanish text for a backend message, or the message itself when it is not a known one. */
export function translateAdminMessage(message: string): string {
  const known = EXACT[message];
  if (known !== undefined) return known;
  if (NETWORK_FAILURES.includes(message)) return 'No se pudo conectar con el servidor.';
  for (const [pattern, build] of PATTERNS) {
    const match = message.match(pattern);
    if (match) return build(match);
  }
  return message;
}
