import { describe, expect, it } from 'vitest';
import { translateAdminMessage } from './messages.js';

describe('translateAdminMessage', () => {
  it('translates the backend messages the admin knows', () => {
    expect(translateAdminMessage('Invalid credentials')).toBe('El correo o la contraseña no son correctos.');
    expect(translateAdminMessage('Slug already exists')).toBe('Ya existe una entrada con ese identificador.');
    expect(translateAdminMessage('You cannot change your own role')).toBe('No puedes cambiar tu propio rol.');
  });

  it('explains a rejected provider key instead of a bare HTTP status', () => {
    expect(translateAdminMessage('List models failed with HTTP 401')).toContain('rechazó la clave');
    expect(translateAdminMessage('List models failed with HTTP 403')).toContain('rechazó la clave');
    expect(translateAdminMessage('List models failed with HTTP 500')).toBe(
      'El proveedor respondió con HTTP 500 al listar los modelos.',
    );
  });

  it('says the provider or the server cannot be reached', () => {
    expect(translateAdminMessage('Network error: ConnectError')).toContain('No se pudo conectar con el proveedor');
    expect(translateAdminMessage('Failed to fetch')).toBe('No se pudo conectar con el servidor.');
    expect(translateAdminMessage('Load failed')).toBe('No se pudo conectar con el servidor.');
  });

  it('translates the pydantic reasons the admin forms can hit', () => {
    expect(translateAdminMessage('String should have at least 8 characters')).toBe('debe tener al menos 8 caracteres');
    expect(translateAdminMessage('Field required')).toBe('es obligatorio');
  });

  it('leaves anything unknown, including Spanish messages, as it came', () => {
    expect(translateAdminMessage('Runs no encontrados en replay_map: x')).toBe('Runs no encontrados en replay_map: x');
  });
});
