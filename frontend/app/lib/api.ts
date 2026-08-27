// Centraliza a URL do backend para evitar hardcoded URLs espalhadas pelo frontend.
// Em produção, configure NEXT_PUBLIC_API_URL via variável de ambiente.
export const API_BASE_URL =
  typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_API_URL
    ? process.env.NEXT_PUBLIC_API_URL
    : 'http://127.0.0.1:8000'
