// Centraliza a URL do backend para evitar hardcoded URLs espalhadas pelo frontend.
// Em produção, configure NEXT_PUBLIC_API_URL via variável de ambiente; sem ela,
// o fallback silencioso 127.0.0.1:8000 vira um log em dev para não passar
// despercebido (backend errado em produção por .env esquecido).
export const API_BASE_URL =
  typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_API_URL
    ? process.env.NEXT_PUBLIC_API_URL
    : 'http://127.0.0.1:8000'

if (process.env.NODE_ENV === 'development' && !(typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_API_URL)) {
  console.info(`[Trivor] Backend em ${API_BASE_URL} — defina NEXT_PUBLIC_API_URL para apontar em outro endereço.`)
}
