export interface SecaoDiagnostico {
  status: 'ok' | 'atencao' | 'critico'
  problema: string
  como_corrigir: string
}

export interface AnalysisResult {
  nota?: number
  resumo_executivo?: string
  pontos_fortes?: string[]
  diagnostico_por_secao?: Record<string, SecaoDiagnostico>
  analise_ats?: {
    score_ats?: number
    palavras_chave_faltantes?: string[]
    gargalos_formatacao?: string[]
    veredito_robos?: string
  } | string
  uso_tokens?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
  api_info?: {
    model: string
    request_id: string
    response_time_ms: number
  }
  error?: string
}

export interface LogEntry {
  id: string
  timestamp: string
  endpoint: string
  method: string
  status_code: number
  duration_ms: number
  error?: string
  ip?: string
}

export interface LogStats {
  total: number
  errors: number
  successes: number
  avg_duration_ms: number
}
