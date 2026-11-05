/// <reference types="vite/client" />

/** Injected by vite.config.ts from the workspace package.json. */
declare const __APP_VERSION__: string;

interface ImportMetaEnv {
  /** `mock` selects the simulated assistant; anything else (or unset) uses the agent runs. */
  readonly VITE_ASSISTANT?: string;
}
