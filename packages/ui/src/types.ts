import type { Component } from 'svelte';

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
