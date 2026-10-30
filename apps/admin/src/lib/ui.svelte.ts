export type ViewId =
  | 'home'
  | 'agent'
  | 'knowledge'
  | 'integrations'
  | 'runs'
  | 'feedback'
  | 'usage'
  | 'providers'
  | 'catalog'
  | 'users'
  | 'audit';

export type ToastKind = 'ok' | 'error';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const TOAST_TTL_MS = 4000;

class UiState {
  view = $state<ViewId>('home');
  toasts = $state<Toast[]>([]);
  // Run that the Runs view should open on its next render (set by links from other views).
  runFocus = $state<string | null>(null);
  private nextToastId = 1;

  switchTo(view: ViewId): void {
    this.view = view;
  }

  openRun(runId: string): void {
    this.runFocus = runId;
    this.view = 'runs';
  }

  notify(message: string, kind: ToastKind = 'ok'): void {
    const id = this.nextToastId++;
    this.toasts = [...this.toasts, { id, kind, message }];
    setTimeout(() => this.dismiss(id), TOAST_TTL_MS);
  }

  dismiss(id: number): void {
    this.toasts = this.toasts.filter((t) => t.id !== id);
  }
}

export const ui = new UiState();
