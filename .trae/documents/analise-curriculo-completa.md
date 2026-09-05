# Plano: Análise de Currículo com Guia de Referência

## Contexto

O analisador de currículos atual retorna um JSON básico (nota, resumo, pontos fortes/fracos, diagnóstico por seção, ATS). O usuário quer que a análise seja **muito mais detalhada**, usando como base o guia de referência em `docs/modulo2_guia_do_aluno_curriculo.md`, que contém:

* **Fórmula XYZ** (impacto mensurado + tecnologias + especificidade)

* **Método STAR** (Situação, Tarefa, Ação, Resultado)

* **Checklist completo** (formatação, header, corpo, seções opcionais)

* **Ordem correta das seções** (profissional vs estudante)

* **Critérios ATS** (PDF com texto selecionável, keywords, formatação simples)

* **Erros comuns** (descrições vagas, parágrafos em vez de bullets, falta de números, abreviações, summary genérico, etc.)

* **Projetos e Networking**

A análise precisa ser **detalhada por seção**, identificar se há foto, analisar cada seção individualmente com problema e como corrigir, contar palavras-chave, mostrar score ATS com justificativa, e dar exemplos práticos.

## Estado Atual

### Backend (`backend/main.py`, linhas 279-311)

* Prompt simples que pede JSON com campos: `nota`, `resumo_executivo`, `pontos_fortes`, `pontos_fracos`, `sugestoes`, `diagnostico_por_secao`, `analise_ats`, `uso_tokens`

* `diagnostico_por_secao` tem apenas: `experiencia`, `educacao`, `habilidades`, `formatacao` — todos com `score` (0-10) e `issues` (array de strings)

* Não há análise de foto, ordem de seções, fórmula XYZ/STAR, erros comuns, ou palavras-chave presentes

### Frontend — Tipos (`frontend/app/types/analysis.ts`)

```ts
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
  uso_tokens?: { prompt_tokens, completion_tokens, total_tokens }
  api_info?: { model, request_id, response_time_ms }
  error?: string
}
```

### Frontend — UI (`frontend/app/page.tsx` e `frontend/app/components/CurriculoTool.tsx`)

* Score circular com nota

* Resumo executivo

* Pontos fortes em grid

* Análise ATS (score, palavras faltantes, gargalos, veredito)

* Diagnóstico por seção (status badge + problema + como corrigir)

* Uso de tokens

* Botões de export (JSON, MD, DOCX, PDF)

## Mudanças Propostas

### 1. Backend — Rewrite do prompt (`backend/main.py`, linhas 279-311)

O prompt será reescrito para instruir a IA a:

1. **Analisar foto**: Detectar se há foto no currículo (indicar presença/ausência)
2. **Verificar ordem das seções**: Comparar com o padrão do guia (profissional vs estudante)
3. **Analisar cada seção individualmente**:

   * **Contato**: Nome, cargo, email, LinkedIn, GitHub, telefone, cidade — tudo presente?

   * **Profile Summary**: Está genérico ("apaixonado por tecnologia") ou específico (cargo + anos + stack)?

   * **Experiência**: Bullet points vs parágrafos? Usa XYZ? Tem números/métricas? Tecnologias listadas?

   * **Educação**: Completa? Datas? Relevante para o cargo?

   * **Skills/Habilidades**: Lista simples ou barras/gráficos (ruim pra ATS)? Tecnologias por extenso?

   * **Projetos**: Links? Descrição com resultado? Relevantes?

   * **Certificações**: Relevantes? Datadas?

   * **Idiomas**: Nível claro (B2, C1, fluente)?
4. **Verificar erros comuns do guia**:

   * Descrição vaga sem métricas

   * Texto em parágrafo ao invés de bullets

   * Abreviações (JS → JavaScript)

   * Motivo de saída (demissão sem justa causa)

   * Summary genérico

   * Muito espaço em branco

   * Tecnologias só na seção de skills
5. **Análise ATS detalhada**:

   * Score 0-100 com pesos: keywords (40%), formatação (30%), seção ordem (15%), presença de métricas (15%)

   * Palavras-chave presentes vs faltantes (comparar com job description se fornecida)

   * Gargalos de formatação específicos

   * Veredito com justificativa
6. **Score geral (0-100)**: Ponderado entre todos os critérios acima

Novo formato JSON retornado:

```json
{
  "nota": 72,
  "score_ats": 52,
  "resumo_executivo": "...",
  "palavras_chave_presentes": ["Python", "PostgreSQL"],
  "palavras_chave_faltantes": ["GraphQL", "Docker"],
  "pontos_fortes": ["..."],
  "pontos_fracos": ["..."],
  "erros_comuns_detectados": [
    { "tipo": "descricao_vaga", "descricao": "...", "exemplo": "..." }
  ],
  "analise_secoes": {
    "contato": { "status": "ok|atencao|critico", "score": 8, "problema": "...", "como_corrigir": "..." },
    "profile_summary": { "status": "critico", "score": 3, "problema": "Summary genérico: 'apaixonado por tecnologia'", "como_corrigir": "Coloque cargo + anos + stack: 'Dev Fullstack com 3 anos em Python/React'" },
    "experiencia": { "status": "atencao", "score": 6, "problema": "Bullet points sem métricas numéricas", "como_corrigir": "Use XYZ: 'Reduzi tempo de carga em 40% implementando cache com Redis'", "has_xyz": false, "has_metrics": false },
    "educacao": { "status": "ok", "score": 9, "problema": null, "como_corrigir": null },
    "habilidades": { "status": "ok", "score": 8, "problema": null, "como_corrigir": null, "ha_barras_graficos": false },
    "projetos": { "status": "ok", "score": 7, "problema": null, "como_corrigir": null, "ha_links": true },
    "certificacoes": { "status": "atencao", "score": 5, "problema": "Certificações sem data", "como_corrigir": "Sempre inclua o ano de obtenção" }
  },
  "ordem_secoes": { "correta": false, "problema": "Educação vem antes de Experiência", "como_corrigir": "Para profissionais com experiência: Contato → Summary → Experiência → Educação → Skills" },
  "foto_detectada": true,
  "foto_recomendada": false,
  "veredito_robos": "com_ressalvas",
  "sugestoes": ["..."],
  "uso_tokens": { "prompt_tokens": 512, "completion_tokens": 385, "total_tokens": 897 },
  "api_info": { "model": "gpt-4o", "request_id": "...", "response_time_ms": 2340 }
}
```

### 2. Frontend — Tipos (`frontend/app/types/analysis.ts`)

Atualizar `AnalysisResult` para incluir os novos campos:

* `score_ats?: number`

* `palavras_chave_presentes?: string[]`

* `erros_comuns_detectados?: Array<{ tipo: string; descricao: string; exemplo?: string }>`

* `analise_secoes?: Record<string, { status: 'ok'|'atencao'|'critico'; score: number; problema?: string|null; como_corrigir?: string|null; has_xyz?: boolean; has_metrics?: boolean; ha_barras_graficos?: boolean; ha_links?: boolean }>`

* `ordem_secoes?: { correta: boolean; problema?: string; como_corrigir?: string }`

* `foto_detectada?: boolean`

* `foto_recomendada?: boolean`

* `palavras_chave_faltantes?: string[]` (já existe em analise\_ats, mas movido para topo)

* `veredito_robos?: string` (mantido em analise\_ats por compatibilidade)

### 3. Frontend — UI em `page.tsx`

Adicionar novas seções nos resultados:

**a) Indicador de foto**

* Badge no topo: "Foto detectada ⚠️" (com warning) ou "Sem foto ✓"

* Texto explicando por que foto não é recomendada para engenharia

**b) Palavra-chave matcher**

* Grid dividido: "Presentes" (verde) e "Faltantes" (vermelho)

* Barra de progresso mostrando % de coverage

**c) Diagnóstico por Seção (expandido)**

* Para cada seção: score numérico (0-10), status badge, problema, como corrigir, e métricas específicas

  * Experiência: mostrar se tem XYZ (✓/✗) e métricas (✓/✗)

  * Habilidades: mostrar se tem barras/gráficos (✓/✗)

  * Projetos: mostrar se tem links (✓/✗)

**d) Erros Comuns detectados**

* Lista com ícone de alerta por cada erro

* Cada erro mostra: tipo, descrição, e exemplo do que está no currículo vs o recomendado

**e) Ordem das seções**

* Veredito: "Ordem correta ✓" ou "Ordem inadequada ✗"

* Explicação do que está errado e qual a ordem ideal

**f) Análise ATS (expandida)**

* Score visual (semicírculo ou barra)

* Breakdown dos pesos: Keywords 40%, Formatação 30%, Ordem 15%, Métricas 15%

* Veredito com justificativa

### 4. Frontend — UI em `CurriculoTool.tsx`

Mesmas atualizações da página `page.tsx`, mantendo consistência visual.

### 5. Backend — Garantir compatibilidade

Manter os campos antigos no JSON (`diagnostico_por_secao`, `analise_ats.palavras_chave_faltantes`, etc.) para não quebrar a UI existente, além dos novos campos. A UI existente já renderiza `diagnostico_por_secao` — o novo `analise_secoes` será uma seção adicional.

## Arquivos a modificar

| Arquivo                                     | O que mudar                                                                       |
| ------------------------------------------- | --------------------------------------------------------------------------------- |
| `backend/main.py` (linhas 279-311)          | Rewrite completo do prompt                                                        |
| `frontend/app/types/analysis.ts`            | Adicionar novos campos em `AnalysisResult`                                        |
| `frontend/app/page.tsx`                     | Adicionar novas seções de UI (foto, keywords, erros comuns, ordem, ATS detalhado) |
| `frontend/app/components/CurriculoTool.tsx` | Mesmas atualizações de UI                                                         |

## Não será feito

* Alterar a lógica de extração de PDF/DOCX (já funciona com docling + fallback pypdfium)

* Alterar o endpoint de exportação

* Alterar a lógica de providers/API keys

## Verificação

1. Iniciar backend e frontend
2. Enviar um currículo de teste
3. Confirmar que o JSON de resposta contém todos os novos campos
4. Confirmar que a UI exibe: foto, palavras-chave, erros comuns, ordem de seções, diagnóstico por seção expandido, ATS detalhado
5. Confirmar que campos antigos continuam funcionando (compatibilidade reversa)

