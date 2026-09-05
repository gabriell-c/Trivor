export interface AnaliseSecao {
  status: 'ok' | 'atencao' | 'critico'
  score: number
  problema?: string | null
  como_corrigir?: string | null
  has_xyz?: boolean
  has_metrics?: boolean
  bullet_points?: boolean
  presente?: boolean
  ha_barras_graficos?: boolean
  ha_links?: boolean
}

export interface ErroComum {
  tipo: string
  descricao: string
  exemplo?: string | null
}

export interface OrdemSecoes {
  correta: boolean
  problema?: string | null
  como_corrigir?: string | null
}

export interface AnaliseATS {
  score_ats: number
  palavras_chave_faltantes?: string[]
  gargalos_formatacao?: string[]
  veredito_robos: 'aprovado' | 'com_ressalvas' | 'reprovado'
  explicacao?: string
}

export interface ChecklistValidacao {
  // Formatação básica
  pdf_selecionavel?: { selecionavel: boolean; problema?: string | null }
  numero_paginas?: number
  numero_paginas_valido?: boolean
  numero_paginas_problema?: string | null
  nome_arquivo?: { valido: boolean; nome: string; problema?: string | null }

  // Dados pessoais
  dados_sensiveis?: Array<{
    tipo: string
    descricao: string
    exemplo?: string
  }>
  motivo_saida?: Array<{
    tipo: string
    descricao: string
    exemplo?: string
  }>

  // Conteúdo
  abreviacoes?: Array<{
    tipo: string
    descricao: string
    exemplo?: string
    sugestao?: string
  }>
  ordem_cronologica?: { cronologica: boolean; problema?: string | null }
  profile_summary?: { genérico: boolean; problema?: string | null; sugestao?: string }
  tech_stack_por_experiencia?: { por_experiencia: boolean; problema?: string | null }
  projetos_com_link?: { com_links: boolean; problema?: string | null }
  multiplos_curriculos?: { multiplos: boolean; nomes_encontrados?: string[]; problema?: string | null }
  cover_letter?: { is_cover_letter: boolean; cover_letter_score?: number; cv_score?: number; problema?: string | null }
}

export interface AnalysisResult {
  nota?: number
  score_ats?: number
  resumo_executivo?: string
  foto_detectada?: boolean
  foto_recomendada?: boolean
  ordem_secoes?: OrdemSecoes
  palavras_chave_presentes?: string[]
  palavras_chave_faltantes?: string[]
  pontos_fortes?: string[]
  pontos_fracos?: string[]
  erros_ortograficos?: Array<{
    palavra: string
    contexto: string
    correcao: string
    gravidade: 'baixa' | 'medio' | 'alta'
  }>
  erros_comuns_detectados?: ErroComum[]
  analise_secoes?: Record<string, AnaliseSecao>
  analise_ats?: AnaliseATS
  diagnostico_por_secao?: Record<string, SecaoDiagnostico>
  sugestoes?: string[]
  checklist_validacao?: ChecklistValidacao
  _links?: string[]
  _extractor_used?: string
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

export interface SecaoDiagnostico {
  status: 'ok' | 'atencao' | 'critico'
  problema: string
  como_corrigir: string
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
  salary_range?: string
  salary_min?: number
  salary_max?: number
  currency?: string
  posted_date?: string
  raw_description?: string
  soft_skills?: string[]
  certifications?: string[]
}

export interface MarketReportSummary {
  job_title: string
  seniority: string
  location: string
  relevant_jobs_analyzed: number
  pre_filtered_count: number
  total_jobs_scanned: number
  discarded_jobs: number
  confidence_score: string
  confidence_reason: string
}

export interface MarketReportStatistics {
  exp_years_median: number
  exp_years_distribution: Record<string, number>
  required_technologies: { name: string; percentage: number; count: number }[]
  desirable_technologies: { name: string; percentage: number; count: number }[]
  modalities: { name: string; percentage: number }[]
  top_soft_skills: { name: string; count: number }[]
  top_certifications: { name: string; count: number }[]
}

export interface MarketReport {
  summary: MarketReportSummary
  statistics: MarketReportStatistics
  vagas: MarketJob[]
  sample_jobs?: MarketJob[]
}

export interface MarketAnalysisResult {
  model: string
  report: MarketReport
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
  model?: string | null
  extractor?: string | null
  fallback_used?: boolean | null
  fallback_level?: string | null
  error?: string | null
  request_body?: string | null
  response_summary?: string | null
  api_key_preview?: string | null
  extracted_text?: string | null
  llm_prompt?: string | null
}

export interface LogStats {
  total: number
  successes: number
  errors: number
  avg_duration_ms: number
}

export interface MarketAnalysis {
  resultado: boolean
  vagas: MarketJob[]
  resumo?: string
  palavras_chave_mais_usadas?: string[]
  niveis_mais_comuns?: string[]
  faixas_salariais?: string[]
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
