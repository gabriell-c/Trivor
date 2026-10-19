import { API_BASE_URL } from './api'

/**
 * Identifica abortes de AbortController (DOMException AbortError no browser
 * ou Error com o mesmo nome). Abort intencional — reinício da mesma feature
 * ou unmount da tela — não é falha e não deve aparecer como erro.
 */
export function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException) return err.name === 'AbortError'
  return err instanceof Error && err.name === 'AbortError'
}

/**
 * Converte erros crus em mensagem PT-BR compreensível para usuário leigo:
 * - falha de rede (TypeError do fetch): indica que o backend pode estar fora;
 * - Error com mensagem (ex.: detalhe HTTP já em PT-BR lançado no fetch):
 *   devolve a própria mensagem;
 * - resto: `detail` (fallback PT-BR específico da chamada) ou genérico.
 */
export function friendlyError(err: unknown, detail?: string): string {
  if (isAbortError(err)) return 'A requisição foi cancelada.'
  if (err instanceof TypeError) {
    return `Não consegui falar com o backend (${API_BASE_URL}). Ele está rodando?`
  }
  if (err instanceof Error && err.message) return err.message
  return detail || 'Algo deu errado. Tente novamente.'
}
