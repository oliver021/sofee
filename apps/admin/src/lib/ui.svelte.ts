export type ViewId = 'providers' | 'catalog' | 'users' | 'audit';

export type ToastKind = 'ok' | 'error';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const TOAST_TTL_MS = 4000;

class UiState {
  view = $state<ViewId>('providers');
  toasts = $state<Toast[]>([]);
  private nextToastId = 1;

  switchTo(view: ViewId): void {
    this.view = view;
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
