interface GoogleAccountsId {
  initialize(opciones: Record<string, unknown>): void
  renderButton(elemento: HTMLElement, opciones: Record<string, unknown>): void
  prompt(): void
  disableAutoSelect(): void
}
interface Window {
  google?: { accounts: { id: GoogleAccountsId } }
}
