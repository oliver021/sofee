export type UserRole = 'admin' | 'regular';

export type ProviderKind = 'vercel_gateway' | 'deepinfra' | 'nvidia_nim' | 'openai_compatible';

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface LoginResponse {
  user: User;
  csrf_token: string;
}

export interface CsrfResponse {
  token: string;
}

export interface CredentialOut {
  id: string;
  last_four: string;
  is_active: boolean;
  created_at: string;
}

export interface CredentialRotateResponse {
  credential: CredentialOut;
  previous_last_four: string | null;
}

export interface Provider {
  id: string;
  name: string;
  kind: ProviderKind;
  base_url: string | null;
  is_enabled: boolean;
  default_headers: Record<string, string> | null;
  credential_last_four: string | null;
  created_at: string;
  updated_at: string;
}

export interface Model {
  id: string;
  provider_id: string;
  model_id: string;
  display_name: string;
  is_enabled: boolean;
}

export interface ConnectionTestResult {
  ok: boolean;
  message: string;
  model_count: number;
}

export interface ModelSyncResult {
  created: number;
  already_exists: number;
  total: number;
  models: Model[];
}

export interface Session {
  id: string;
  created_at: string;
  expires_at: string;
  user_agent: string | null;
  ip_address: string | null;
}

export interface AuditEntry {
  id: number;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  metadata: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditPage {
  items: AuditEntry[];
  next_cursor: string | null;
}

export interface ApiErrorLike {
  status: number;
  message: string;
}

export interface PublicProviderModel {
  id: string;
  provider_id: string;
  provider_name: string;
  model_id: string;
  display_name: string;
}

export interface CatalogBinding {
  id: string;
  provider_model_id: string;
  provider_id: string;
  provider_name: string;
  model_id: string;
  model_display_name: string;
  priority: number;
  is_enabled: boolean;
  is_available: boolean;
}

export interface CatalogEntry {
  id: string;
  slug: string;
  display_name: string;
  description: string | null;
  category: string;
  is_enabled: boolean;
  sort_order: number;
  is_available: boolean;
  created_at: string;
  updated_at: string;
  bindings: CatalogBinding[];
}
