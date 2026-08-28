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
  }
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

export interface MarketJob {
  title: string
  company: string
  location: string
  modality: string
  source: string
  source_url: string
  is_relevant: boolean
  requirements: string[]
  nice_to_have: string[]
  role_level: string | null
  exp_years_min: number | null
  exp_years_max: number | null
  soft_skills: string[]
  certifications: string[]
  salary_min: number | null
  salary_max: number | null
  currency: string | null
  raw_description: string
}

export interface MarketReport {
  summary: {
    job_title: string
    target_stack: string[]
    seniority: string
    location: string
    time_window: string
    total_jobs_scanned: number
    pre_filtered_count: number
    relevant_jobs_analyzed: number
    discarded_jobs: number
    confidence_score: string
    confidence_reason: string
    generated_at: string
  }
  statistics: {
    required_technologies: { name: string; count: number; percentage: number }[]
    desirable_technologies: { name: string; count: number; percentage: number }[]
    exp_years_median: number
    exp_years_distribution: Record<string, number>
    modalities: { name: string; count: number; percentage: number }[]
    top_soft_skills: { name: string; count: number }[]
    top_certifications: { name: string; count: number }[]
  }
  sample_jobs: MarketJob[]
}

export interface MarketAnalysisResult {
  success: boolean
  report: MarketReport
  elapsed_seconds: number
  model: string
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
