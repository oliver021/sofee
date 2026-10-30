/**
 * Which assistant the app talks to. `VITE_ASSISTANT=mock` keeps the simulated reply path that
 * needs no backend (packages/core's mock stream, with its simulated failures). Anything else runs
 * replies through the server's agent runs (roadmap §3.7).
 */
export const isMockAssistant: boolean = import.meta.env.VITE_ASSISTANT === 'mock';
