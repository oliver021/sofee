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
  // Aptitud para agentes. `supports_tools` lo fija la prueba del catálogo; null = no probado.
  supports_tools: boolean | null;
  context_window: number | null;
  input_price_per_mtok: number | null;
  output_price_per_mtok: number | null;
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
  // Capacidades del modelo del binding (se editan en el admin de providers).
  supports_tools: boolean | null;
  context_window: number | null;
  input_price_per_mtok: number | null;
  output_price_per_mtok: number | null;
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
  // Apta para el agente: hay un binding disponible y todos los disponibles admiten tools.
  agent_ready: boolean;
  context_window: number | null;
  created_at: string;
  updated_at: string;
  bindings: CatalogBinding[];
}

// --- agent admin (apps/api/app/schemas/agent_admin.py) -----------------------------------

export type AgentMode = 'learn' | 'research' | 'explore';

export type AgentToolName =
  'search_team_docs' | 'web_search' | 'suggest_directions' | 'check_understanding';

export interface AgentSubagentConfig {
  name: string;
  description: string;
  system_prompt: string;
  tools: AgentToolName[];
  planning: boolean;
}

export interface AgentLimits {
  max_steps: number;
  max_seconds: number;
  max_subagents: number;
  max_searches: number;
}

export interface AgentProfileConfig {
  tools: AgentToolName[];
  planning: boolean;
  plan_review: boolean;
  subagents: AgentSubagentConfig[];
  limits: AgentLimits;
}

// id, version and created_at are null for the code default (no row in the database).
export interface AgentProfileVersion {
  id: string | null;
  version: number | null;
  is_active: boolean;
  system_prompt: string;
  config: AgentProfileConfig;
  created_by_email: string | null;
  created_at: string | null;
}

export interface AgentProfile {
  mode: AgentMode;
  active: AgentProfileVersion;
  history: AgentProfileVersion[];
}

// Mode -> locale -> starter texts. An empty list means the client uses its own i18n starters.
export type AgentStarters = Partial<Record<AgentMode, Partial<Record<string, string[]>>>>;

export interface AgentReplayEntry {
  prompt: string;
  run_id: string;
}

export interface AgentQuotaLimits {
  runs_per_day: number | null;
  tokens_per_day: number | null;
}

export interface AgentSettings {
  enabled: boolean;
  starters: AgentStarters;
  replay_map: AgentReplayEntry[];
  quotas: Partial<Record<UserRole, AgentQuotaLimits>>;
}

export type AgentRunStatus =
  'queued' | 'running' | 'interrupted' | 'completed' | 'failed' | 'cancelled';

export interface AdminRun {
  id: string;
  thread_id: string;
  user_id: string;
  user_email: string | null;
  kind: string;
  mode: AgentMode;
  status: AgentRunStatus;
  catalog_slug: string | null;
  model_label: string | null;
  provider_model_id: string | null;
  error_code: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_estimate: number | null;
  ttft_ms: number | null;
  duration_ms: number | null;
  hallucinated_citations: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AdminRunPage {
  items: AdminRun[];
  next_cursor: string | null;
}

export interface RunEvent {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
}

export interface AdminRunDetail extends AdminRun {
  question: string | null;
  answer: string | null;
  citations: Record<string, unknown>[] | null;
  error_message: string | null;
  profile_version_id: string | null;
  profile_version: number | null;
  trace_url: string | null;
  events: RunEvent[];
}

export type FeedbackValue = 'good' | 'bad';

export interface AdminFeedback {
  id: string;
  value: FeedbackValue;
  reason: string | null;
  comment: string | null;
  reviewed: boolean;
  reviewed_at: string | null;
  created_at: string;
  user_email: string | null;
  thread_id: string;
  message_id: string;
  run_id: string | null;
  question: string | null;
  answer: string;
}

export interface AdminFeedbackPage {
  items: AdminFeedback[];
  next_cursor: string | null;
}

export interface UsageTotals {
  runs: number;
  input_tokens: number;
  output_tokens: number;
  cost_estimate: number;
  failed_runs: number;
  error_rate: number | null;
  hallucinated_citations: number;
}

export interface LatencyStats {
  duration_p50_ms: number | null;
  duration_p95_ms: number | null;
  ttft_p50_ms: number | null;
  ttft_p95_ms: number | null;
}

export interface UsageDayRow {
  day: string;
  catalog_slug: string | null;
  model_label: string | null;
  runs: number;
  input_tokens: number;
  output_tokens: number;
  cost_estimate: number;
}

export interface UsageModelRow {
  catalog_slug: string | null;
  model_label: string | null;
  runs: number;
  input_tokens: number;
  output_tokens: number;
  cost_estimate: number;
}

export interface UsageBindingRow {
  provider_model_id: string | null;
  provider_name: string | null;
  model_id: string | null;
  runs: number;
  failed_runs: number;
  error_rate: number | null;
  latency: LatencyStats;
}

export interface UsageReport {
  days: number;
  since: string;
  totals: UsageTotals;
  latency: LatencyStats;
  daily: UsageDayRow[];
  by_model: UsageModelRow[];
  bindings: UsageBindingRow[];
}

export type ProbeVerdict = 'supports' | 'no_tool_call' | 'rejected' | 'inconclusive' | 'skipped';

export interface AgentTestResult {
  binding_id: string;
  provider_model_id: string;
  provider_name: string;
  model_id: string;
  verdict: ProbeVerdict;
  supports_tools: boolean | null;
  message: string;
  latency_ms: number | null;
}

export interface AgentTestOutcome {
  results: AgentTestResult[];
  agent_ready: boolean;
  entry: CatalogEntry;
}

// --- knowledge base and integrations ----------------------------------------------------

export interface KbDocument {
  id: string;
  slug: string;
  title: string;
  path: string;
  source_filename: string;
  content_type: string;
  size_bytes: number;
  tags: string[];
  is_enabled: boolean;
  // 0 means the file had no text layer (for example a scanned PDF): the agent cannot read it.
  text_chars: number;
  created_at: string;
  updated_at: string;
}

// `reason` is a code: unsupported_type, too_large or extraction_failed.
export interface KbRejectedFile {
  filename: string;
  reason: string;
}

export interface KbUploadResult {
  documents: KbDocument[];
  rejected: KbRejectedFile[];
}

export interface KbText {
  id: string;
  title: string;
  text: string;
  text_chars: number;
  truncated: boolean;
}

export interface TavilyStatus {
  configured: boolean;
  last_four: string | null;
  updated_at: string | null;
}

export interface TavilyTestResult {
  ok: boolean;
  message: string;
}
