# Plano: Aba de Análise de Perfil LinkedIn

## Resumo

Adicionar uma nova aba **"Análise de LinkedIn"** ao Trivor. O usuário cola o texto da página do LinkedIn (Ctrl+A → Ctrl+V) e opcionalmente uma foto de perfil. A IA analisa o perfil com grounding estrito (sem inventar dados), gerando score, diagnóstico por seção e melhorias — seguindo o mesmo padrão da análise de currículo.

***

## Análise do Estado Atual

### Frontend

* **Navegação**: `frontend/app/components/Layout.tsx` — tools: `curriculo | mercado | dashboard | api-settings | logs`

* **Shell**: `frontend/app/components/AppShell.tsx` — carrega páginas via `dynamic()`

* **Página de currículo**: `frontend/app/page.tsx` — step 1 (input) → step 2 (resultados), usa `getBestProvider(['curriculo'])`

* **Página de mercado**: `frontend/app/market/page.tsx` — tabs config/results/jobs, padrão de exportação

* **Providers IA**: `frontend/app/hooks/useIaProviders.ts` — `getBestProvider(tools)` com valores `'all' | 'curriculo' | 'market' | 'none'`

### Backend

* **Endpoints**: `backend/main.py` — `POST /api/analyze` (currículo), `POST /api/market/analyze` (mercado)

* **Chamada LLM**: `openai.OpenAI` com `response_format: json_object`

* **System prompt**: `knowledge/system_prompt.md` — regras de análise de currículo

* **Provider selection**: `_get_provider_for_tool()` no backend

### Documento guia (extraído do PDF)

`docs/linkedin_guide.txt` (14.570 chars, 13 páginas) — contém:

* **Foto**: Rosto nítido, fundo neutro, leve sorriso, profissional

* **Headline**: Cargo + @empresa | 3-5 tecnologias principais (SEO do perfil)

* **About**: Anos de XP, tipo de produto, resultado/escala, lista de techs no final

* **Experiências**: Bullet points, fórmula XYZ (ação + tecnologia + resultado mensurável), skills por experiência, tech stack, datas corretas

* **Skills**: 30+ skills, top 5 por relevância, assessments, educação, certificações, featured, idiomas

* **Visibilidade**: Open to Work (recrutadores), seguir empresas-alvo, SSI score

### Exemplo de texto colado

`docs/exemplo_linkedin.txt` — mostra a estrutura real do LinkedIn com:

* Header/navegação (lixo): "0 notificação", "Pesquisar", "Início", "Minha rede", etc.

* Seções válidas: nome, headline, localização, Sobre, Experiência, Formação, Certificações, Projetos, Competências, Idiomas

* Lixo para descartar: footer, "Quem seus visitantes também viram", "Você talvez goste", "Pessoas que talvez você conheça"

***

## Mudanças Propostas

### 1. Novo Prompt de Sistema para LinkedIn

**Arquivo**: `knowledge/linkedin_prompt.md`

Criar prompt específico para análise de LinkedIn, seguindo princípios do `system_prompt.md` (grounding estrito, precisão). O prompt deve:

* Instruir a IA a identificar e descartar lixo do LinkedIn (header, footer, recomendações, "pessoas que talvez você conheça", etc.)

* Definir regras de extração de seções: nome, headline, sobre, experiência, educação, habilidades, certificações, projetos, idiomas

* Aplicar as mesmas regras de qualidade do currículo (fórmula XYZ, sem clichês, etc.)

* Adicionar regras específicas de LinkedIn: headline como SEO, about com escala/resultados, 30+ skills, Open to Work

* Referenciar o guia de `docs/linkedin_guide.txt`

* Definir estrutura JSON de saída idêntica à do currículo (para reusar frontend)

### 2. Backend — Endpoint `/api/linkedin/analyze`

**Arquivo**: `backend/main.py`

Novo endpoint `POST /api/linkedin/analyze` recebendo:

* `text`: string (Form) — texto colado do LinkedIn

* `image_url`: string (Form, opcional) — URL da foto de perfil

* `api_key`, `api_url`, `model_name`, `provider_id`: credenciais IA (mesmo padrão)

Comportamento:

* Montar system prompt de `knowledge/linkedin_prompt.md`

* Montar user prompt com o texto colado + instruções de limpeza

* Se `image_url` fornecido e modelo suporta visão (gpt-4o), incluir imagem na chamada

* Se não suporta, ignorar imagem com nota no resultado

* Chamar LLM com `response_format: json_object`

* Retornar JSON com a mesma estrutura do `/api/analyze`

### 3. Frontend — Página `linkedin/page.tsx`

**Arquivo**: `frontend/app/linkedin/page.tsx` (novo)

Interface com duas etapas (step 1 → step 2, igual ao currículo):

**Step 1 (Input):**

* Textarea grande (min-h-48) com placeholder: "Cole aqui o conteúdo da página do LinkedIn (Ctrl+A → Ctrl+V)..."

* Área de foto de perfil com 3 métodos:

  1. **Paste**: detectar `onPaste` com `clipboardData.items` (image/png)
  2. **Drag & drop**: area com `onDrop` e `onDragOver`
  3. **URL**: input text para colar link da imagem

* Pré-visualização da foto (thumbnail) se fornecida

* Botão "Analisar Perfil" (disabled se texto vazio)

**Step 2 (Resultados):**

* Score geral (badge grande, mesmo estilo do currículo)

* Resumo executivo

* Pontos fortes

* Diagnóstico por seção (reusar `renderDiagnostico`):

  * `foto_perfil` — status da foto

  * `headline` — qualidade do título

  * `sobre` — qualidade do resumo

  * `experiencias` — fórmula XYZ, métricas

  * `educacao` — completude

  * `habilidades` — quantidade e relevância

  * `certificacoes` — presença

  * `idiomas` — presença

  * `visibilidade` — Open to Work, SSI

* Palavras-chave faltantes

* Veredito geral

* Botão "Nova análise" (volta ao step 1)

* Botões de exportação (MD/DOCX/PDF)

### 4. Navegação

**Arquivo**: `frontend/app/components/Layout.tsx`

Adicionar na lista de tools:

```ts
{ id: 'linkedin', label: 'Análise de LinkedIn', icon: <Users className="w-5 h-5" />, description: 'Diagnóstico de perfil LinkedIn' }
```

**Arquivo**: `frontend/app/components/AppShell.tsx`

* Adicionar `'linkedin'` ao type `Tool`

* Importar dynamic: `const LinkedinPage = dynamic(() => import('../linkedin/page').then(m => m.default), { ssr: false })`

* Adicionar render: `{activeTool === 'linkedin' && (<motion.div key="linkedin" ...><LinkedinPage /></motion.div>)}`

### 5. Provider para LinkedIn

**Arquivo**: `frontend/app/hooks/useIaProviders.ts`

Atualizar `getBestProvider` para suportar `'linkedin'` como tool. Como LinkedIn e currículo usam a mesma IA, o provider com `usedFor === 'all'` ou `usedFor === 'curriculo'` funciona.

**Arquivo**: `backend/main.py`

Atualizar `_get_provider_for_tool` para suportar `'linkedin'` (fallback para `'curriculo'`).

***

## Estrutura de Arquivos

```
backend/
  main.py                      # +POST /api/linkedin/analyze

knowledge/
  linkedin_prompt.md           # Novo: prompt de análise LinkedIn

frontend/
  app/
    linkedin/
      page.tsx                 # Novo: página de análise LinkedIn
    components/
      Layout.tsx               # +item LinkedIn na sidebar
      AppShell.tsx             # +tool 'linkedin' + dynamic import
    hooks/
      useIaProviders.ts        # + 'linkedin' nos tools
```

***

## JSON de Saída (mesma estrutura do currículo)

```json
{
  "nota": 7.5,
  "resumo_executivo": "Parecer geral sobre o perfil LinkedIn.",
  "pontos_fortes": ["Headline otimizada com keywords", "Experiências com métricas"],
  "diagnostico_por_secao": {
    "foto_perfil": { "status": "ok", "problema": "", "como_corrigir": "" },
    "headline": { "status": "atencao", "problema": "Faltam keywords de busca", "como_corrigir": "Adicione 3-5 tecnologias principais" },
    "sobre": { "status": "ok", "problema": "", "como_corrigir": "" },
    "experiencias": { "status": "critico", "problema": "Bullets descritivos sem métricas", "como_corrigir": "Aplique fórmula XYZ" },
    "educacao": { "status": "ok", "problema": "", "como_corrigir": "" },
    "habilidades": { "status": "atencao", "problema": "Apenas 15 skills", "como_corrigir": "Adicione 30+ skills no perfil" },
    "certificacoes": { "status": "ok", "problema": "", "como_corrigir": "" },
    "idiomas": { "status": "ok", "problema": "", "como_corrigir": "" },
    "visibilidade": { "status": "atencao", "problema": "Open to Work desativado", "como_corrigir": "Ative para recrutadores" }
  },
  "analise_ats": {
    "score_ats": 7.0,
    "palavras_chave_faltantes": ["Docker", "AWS", "CI/CD"],
    "gargalos_formatacao": [],
    "veredito_robos": "Perfil com boa estrutura mas lacunas em keywords técnicas."
  },
  "uso_tokens": { "prompt_tokens": 1200, "completion_tokens": 400, "total_tokens": 1600 },
  "api_info": { "model": "gpt-4o", "request_id": "...", "response_time_ms": 2300 }
}
```

***

## Limpeza de Texto (no prompt, não no frontend)

A IA receberá o texto bruto e deverá:

1. Identificar seções válidas (nome, headline, sobre, experiências, etc.)
2. Descartar lixo: header de navegação ("Início", "Minha rede", "Vagas"), footer, recomendações ("pessoas que talvez você conheça"), "vocês talvez goste", métricas de visualização, etc.
3. Usar apenas o conteúdo relevante para análise
4. NÃO inventar dados que não estão no texto

***

## Verificação

1. Testar endpoint `POST /api/linkedin/analyze` com `exemplo_linkedin.txt`
2. Verificar que a IA descarta corretamente o lixo (footer, header, recomendações)
3. Verificar que a análise segue o guia (headline SEO, fórmula XYZ, 30+ skills)
4. Verificar upload de imagem (paste, drag & drop, URL)
5. Verificar navegação na sidebar
6. Verificar que o score e diagnóstico são fundamentados (sem invenção)
7. Verificar exportação MD/DOCX/PDF

