/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `mock` selects the simulated assistant; anything else (or unset) uses the agent runs. */
  readonly VITE_ASSISTANT?: string;
}
