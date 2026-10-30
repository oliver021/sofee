/**
 * The model selector's data: `GET /catalog` (the curated, admin-built catalog — never the raw
 * provider/model inventory) plus the user's choice, persisted in localStorage. The choice travels
 * with each run as `model_slug`. With the agent, only entries marked `agent_ready` are offered
 * (they support the tool calling a deep agent needs); the mock assistant keeps its old list.
 */
import { api } from './api.js';
import { isMockAssistant } from './assistant-mode.js';

export interface ModelOption {
  /** The catalog entry's stable slug — never a provider or model id. */
  readonly id: string;
  readonly label: string;
}

interface PublicCatalogEntry {
  id: string;
  slug: string;
  display_name: string;
  description: string | null;
  category: string;
  is_available: boolean;
  agent_ready: boolean;
  context_window: number | null;
}

const STORAGE_KEY = 'sofee:selected-model';

function readStoredModel(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredModel(id: string | null): void {
  try {
    if (id === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Private browsing / disabled storage: model choice is a convenience, not worth surfacing.
  }
}

class ModelState {
  options = $state<ModelOption[]>([]);
  selectedId = $state<string | null>(readStoredModel());
  loading = $state(false);
  loaded = $state(false);

  get selected(): ModelOption | null {
    return this.options.find((option) => option.id === this.selectedId) ?? null;
  }

  async load(): Promise<void> {
    this.loading = true;
    try {
      const rows = await api<PublicCatalogEntry[]>('/catalog');
      this.options = rows
        .filter((row) => (isMockAssistant ? row.is_available : row.agent_ready))
        .map((row) => ({
          id: row.slug,
          label: row.display_name,
        }));
      if (this.selectedId && !this.options.some((o) => o.id === this.selectedId)) {
        this.selectedId = null;
      }
      if (!this.selectedId && this.options[0]) {
        this.select(this.options[0].id);
      }
      this.loaded = true;
    } finally {
      this.loading = false;
    }
  }

  select(id: string): void {
    this.selectedId = id;
    writeStoredModel(id);
  }

  reset(): void {
    this.options = [];
    this.loaded = false;
  }
}

export const models = new ModelState();
