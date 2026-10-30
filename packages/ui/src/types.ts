import type { Component } from 'svelte';
import type { Citation } from '@sofee/core';

/**
 * Shapes shared between a few components in this package. These describe UI
 * configuration (what a toolbar button or menu item looks like and does), not
 * application data — packages/ui owns no domain state, so callers (apps/web)
 * decide what `onActivate` actually does.
 */

export interface ToolbarItem {
  id: string;
  icon: Component<{ size?: number }>;
  label: string;
  tooltip?: string;
  active?: boolean;
  badge?: number;
  ariaHasPopup?: 'menu' | 'dialog';
  ariaExpanded?: boolean;
  /** Receives the button element so a menu/panel-opening caller can use it as the anchor and,
   * later, the focus-return target — see Menu's and OverlayPanel's `anchor`/`triggerEl`. */
  onActivate: (buttonEl: HTMLButtonElement) => void;
}

export interface MenuItemConfig {
  id: string;
  label: string;
  icon?: Component<{ size?: number }>;
  shortcut?: string;
  destructive?: boolean;
  checked?: boolean;
  /** Set on a drill-down item (e.g. "Language" opening a submenu view in place) so activating
   * it swaps the menu's item list instead of closing the menu. */
  keepOpen?: boolean;
  onActivate: () => void;
}

/*
 * View models for the agent's surface (roadmap §5, U2–U18). apps/web builds them from the run
 * state, with every label already translated, so these components only lay strings out. Anything
 * that needs a decision (what counts as a step, how a tool is grouped) is made before it gets here.
 */

export type PlanStepStatus = 'pending' | 'in_progress' | 'completed';

export interface PlanStepView {
  readonly content: string;
  readonly status: PlanStepStatus;
  /** Spoken alongside the step's glyph, e.g. "Done" or "In progress". */
  readonly statusLabel: string;
}

export interface PlanView {
  readonly steps: readonly PlanStepView[];
  readonly running: boolean;
  /** While running: "Working · step 2 of 5". */
  readonly headline: string;
  /** Once finished, the one-line summary: "5 steps · 12 sources · 48 s". */
  readonly summary: string;
  /** While running, the live source count, e.g. "3 sources". Null when there are none yet. */
  readonly liveSources: string | null;
}

export type AgentStatus = 'running' | 'success' | 'error';

export interface SubagentView {
  readonly id: string;
  readonly name: string;
  readonly task: string;
  readonly status: AgentStatus;
  readonly statusLabel: string;
  readonly summary: string | null;
}

export interface SourceView {
  readonly index: number;
  readonly title: string;
  /** Where the source lives: the host of a web page, or "Team document" / "Attachment". */
  readonly meta: string;
  readonly snippet: string | null;
  readonly citation: Citation;
}

export interface ToolRowView {
  readonly id: string;
  readonly name: string;
  readonly argsPreview: string;
  readonly status: AgentStatus;
  readonly statusLabel: string;
  readonly durationLabel: string;
}

export interface ToolGroupView {
  readonly key: string;
  readonly label: string;
  /** The main agent's calls are shown open and are not collapsible; subagents' are. */
  readonly main: boolean;
  readonly rows: readonly ToolRowView[];
}

export interface ToolRunView {
  readonly runId: string;
  readonly title: string;
  readonly groups: readonly ToolGroupView[];
}

export interface AgentFileView {
  readonly path: string;
  readonly name: string;
  readonly sizeLabel: string;
}

export interface AgentFilePreview {
  readonly path: string;
  readonly name: string;
  /** Null while loading or after a failure. */
  readonly content: string | null;
  readonly loading: boolean;
  readonly error: boolean;
}
