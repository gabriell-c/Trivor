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

  // Métricas e resultados
  metrics?: AnaliseSecao
  github_metrics?: AnaliseSecao
  linkedin_metrics?: AnaliseSecao

  // Experiência
  experiencias?: Array<{
    presente?: boolean
    tempo?: string
    problemas?: Array<{
      tipo: string
      descricao: string
      como_corrigir: string
    }>
  }>

  // Formação
  formacao?: Array<{
    presente?: boolean
    tempo?: string
    problema?: string | null
    como_corrigir?: string | null
  }>

  // Links
  links?: Array<{
    tipo: string
    valido: boolean
    problema?: string | null
  }>
}

export interface SecaoInfo {
  nome: string
  Score: number
  status: 'ok' | 'atencao' | 'critico'
  problema?: string | null
  como_corrigir?: string | null
}

export interface Recomendacao {
  titulo: string
  descricao: string
  prioridade: 'alta' | 'media' | 'baixa'
  categoria: string
}

export interface ScoreDetalhado {
  secao: string
  Score: number
  max_score: number
  comentarios?: string[]
}

export interface AnaliseGeral {
  score_geral: number
 score_ats: AnaliseATS
  ordem_secoes: OrdemSecoes
  secoes_analisadas: Array<{
    nome: string
    status: 'ok' | 'atencao' | 'critico'
    score: number
    porcentagem?: number
  }>
  recomendacoes: Recomendacao[]
  resumo_executivo: string
  erros_comuns: ErroComum[]
}

export interface DadosPessoais {
  nome?: string
  email?: string
  telefone?: string
  linkedin?: string
  github?: string
  localizacao?: string
}

export interface Experiencia {
  empresa: string
  cargo: string
  periodo: string
  responsavel?: string
  descricao?: string
  tecnologias?: string[]
}

export interface Formacao {
  instituicao: string
  curso: string
  periodo: string
  grau?: string
}

export interface Projeto {
  nome: string
  descricao: string
  tecnologias?: string[]
  link?: string
}

export interface Competencia {
  nome: string
  nivel?: string
}

export interface Certificação {
  nome: string
  emissor?: string
  periodo?: string
}

export interface Idioma {
  idioma: string
  nivel?: string
}

export interface ResumeData {
  dados_pessoais?: DadosPessoais
  perfil_profissional?: string
  experiencias?: Experiencia[]
  formacoes?: Formacao[]
  projetos?: Projeto[]
  competencias?: Competencia[]
  certificacoes?: Certificação[]
  idiomas?: Idioma[]
  informacoes_adicionais?: string
}

export interface ResumeAnalysis {
  score_geral: number
  score_ats: AnaliseATS
  secoes_analisadas: Array<{
    nome: string
    status: 'ok' | 'atencao' | 'critico'
    score: number
    porcentagem?: number
  }>
  recomendacoes: Recomendacao[]
  resumo_executivo: string
  erros_comuns: ErroComum[]
}

// Market Intelligence Types
export interface MarketJob {
  title: string
  company: string
  location: string
  modality: string
  source: string
  source_url: string
  is_relevant: boolean
  rejection_reason?: string | null
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
  rejected_reasons_sample?: { title: string; reason: string }[]
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
  top_languages: { name: string; count: number; top_level: string }[]
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
}
