import type { Translate } from '@sofee/core';

export interface ShortcutRow {
  readonly keys: string;
  readonly description: string;
}

/** One keyboard reference for both the standalone Shortcuts dialog and Settings > Shortcuts. */
export function shortcutRows(t: Translate): ShortcutRow[] {
  const isMac =
    typeof navigator !== 'undefined' &&
    /Mac|iPhone|iPad/.test(navigator.platform ?? navigator.userAgent ?? '');
  const mod = isMac ? '⌘' : 'Ctrl';

  return [
    { keys: `${mod} K`, description: t('commandPalette.title') },
    { keys: `${mod} N`, description: t('shortcuts.newChat') },
    { keys: `${mod} ⇧ N`, description: t('shortcuts.newTemporaryChat') },
    { keys: `${mod} J`, description: t('shortcuts.toggleChats') },
    { keys: `${mod} ,`, description: t('shortcuts.openSettings') },
    { keys: `${mod} /`, description: t('shortcuts.shortcutsDialog') },
    { keys: 'Esc', description: t('shortcuts.closeOrStop') },
    { keys: '↑', description: t('shortcuts.editLastMessage') },
    { keys: 'Alt ↑ / ↓', description: t('shortcuts.moveBetweenMessages') },
  ];
}
