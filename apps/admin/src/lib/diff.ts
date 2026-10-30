// Line diff for the prompt-version comparison. Plain LCS: prompts are a few hundred lines at most,
// so the quadratic table is cheap and keeps this free of dependencies.

export interface DiffCell {
  kind: 'same' | 'add' | 'del';
  text: string;
}

export interface SideRow {
  left: DiffCell | null;
  right: DiffCell | null;
}

type Op = DiffCell;

function lcsOps(a: string[], b: string[]): Op[] {
  const n = a.length;
  const m = b.length;
  // table[i][j] = LCS length of a[i..] and b[j..].
  const table: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    const row = table[i] ?? [];
    const below = table[i + 1] ?? [];
    for (let j = m - 1; j >= 0; j--) {
      row[j] = a[i] === b[j] ? (below[j + 1] ?? 0) + 1 : Math.max(below[j] ?? 0, row[j + 1] ?? 0);
    }
  }

  const ops: Op[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    const current = a[i] ?? '';
    const other = b[j] ?? '';
    if (current === other) {
      ops.push({ kind: 'same', text: current });
      i++;
      j++;
    } else if ((table[i + 1]?.[j] ?? 0) >= (table[i]?.[j + 1] ?? 0)) {
      ops.push({ kind: 'del', text: current });
      i++;
    } else {
      ops.push({ kind: 'add', text: other });
      j++;
    }
  }
  while (i < n) {
    ops.push({ kind: 'del', text: a[i] ?? '' });
    i++;
  }
  while (j < m) {
    ops.push({ kind: 'add', text: b[j] ?? '' });
    j++;
  }
  return ops;
}

// Side-by-side rows: unchanged lines on both sides; a block of removed and added lines is paired
// row by row, so a rewritten line shows the old text on the left and the new text on the right.
export function sideBySide(oldText: string, newText: string): SideRow[] {
  const ops = lcsOps(oldText.split('\n'), newText.split('\n'));
  const rows: SideRow[] = [];
  let removed: string[] = [];
  let added: string[] = [];

  const flush = () => {
    const count = Math.max(removed.length, added.length);
    for (let k = 0; k < count; k++) {
      const del = removed[k];
      const add = added[k];
      rows.push({
        left: del === undefined ? null : { kind: 'del', text: del },
        right: add === undefined ? null : { kind: 'add', text: add },
      });
    }
    removed = [];
    added = [];
  };

  for (const op of ops) {
    if (op.kind === 'same') {
      flush();
      rows.push({ left: op, right: op });
    } else if (op.kind === 'del') {
      removed.push(op.text);
    } else {
      added.push(op.text);
    }
  }
  flush();
  return rows;
}
