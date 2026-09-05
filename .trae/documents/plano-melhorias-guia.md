# Plano de Implementação: Análise de Currículos Completa

## Resumo
Implementar todas as estratégias, conceitos, dicas e técnicas do guia `modulo2_guia_do_aluno_curriculo.md` no sistema de análise de currículos, mantendo a abrangência para todas as áreas (não apenas dev/tech).

---

## Estado Atual

### O que JÁ funciona:
- ✅ Fórmula XYZ do Google (analisada)
- ✅ Método STAR (analisado)
- ✅ Análise ATS básica
- ✅ Proteção contra erros ortográficos falsos
- ✅ Anti-viés dev/tech
- ✅ Regras de capitalização
- ✅ Análise de seções básicas

### O que FALTA implementar (do guia):
1. **Verificação de nome do arquivo** — padrão: SeuNome_CV.pdf
2. **Verificação de páginas** — 1 página (até ~5 anos exp) ou máximo 2
3. **Verificação de PDF selecionável** — Ctrl+F funciona
4. **Verificação de ordem cronológica reversa** — experiências mais recentes primeiro
5. **Verificação de abreviações** — JS → JavaScript, etc.
6. **Verificação de dados sensíveis** — CPF, RG, CTPS, dados bancários
7. **Verificação de motivo de saída** — "demissão sem justa causa"
8. **Verificação de projetos com link** — link deve estar presente
9. **Verificação de Profile Summary genérico** — "apaixonado por tecnologia"
10. **Verificação de múltiplos currículos** — quando faz sentido
11. **Verificação de Cover Letter** — estrutura e exemplos
12. **Verificação de formatação** — fonte preta, fundo branco, tipografia comum
13. **Verificação de tech stack por experiência** — tecnologias mencionadas em cada experiência

---

## Arquivos a Modificar

### 1. `knowledge/cv_analysis_prompt.md`
**Objetivo:** Atualizar o prompt da LLM para incluir todas as regras do guia.

**Alterações:**
- Adicionar seção "CHECKLIST COMPLETO DO GUIA"
- Adicionar regras para cada item faltante
- Reforçar que a análise deve ser para QUALQUER área
- Adicionar exemplos de erros comuns do guia

### 2. `backend/main.py`
**Objetivo:** Adicionar validações específicas no código (não apenas via LLM).

**Novas funções:**
```python
def _check_pdf_selectable(pdf_path: str) -> bool:
    """Verifica se o PDF é selecionável (Ctrl+F funciona)"""
    # Usar PyMuPDF para verificar se há texto selecionável

def _count_pdf_pages(pdf_path: str) -> int:
    """Conta número de páginas do PDF"""
    # Usar PyMuPDF ou pypdfium2

def _detect_sensitive_data(text: str) -> dict:
    """Detecta CPF, RG, CTPS, dados bancários"""
    # Regex para CPF, RG, CTPS
    # Regex para dados bancários (agência, conta, banco)

def _detect_abbreviations(text: str) -> list:
    """Detecta abreviações que só o candidato entende"""
    # Lista de abreviações comuns: JS, HTML, CSS, etc.
    # Verificar se estão escritas por extenso

def _check_chronological_order(text: str) -> dict:
    """Verifica se experiências estão em ordem cronológica reversa"""
    # Extrair datas das experiências
    # Verificar se estão ordenadas do mais recente para o mais antigo

def _check_projects_have_links(text: str, links_info: list) -> dict:
    """Verifica se projetos têm links"""
    # Encontrar seção de projetos
    # Verificar se há URLs nos bullets

def _check_profile_summary(text: str) -> dict:
    """Verifica se Profile Summary é genérico"""
    # Palavras-chave de resumo genérico: apaixonado, adoro, etc.

def _check_tech_stack_by_experience(text: str) -> dict:
    """Verifica se tecnologias são citadas em cada experiência"""
    # Para cada experiência, verificar se há tecnologias listadas
```

**Modificações no endpoint `analyze_cv`:**
- Adicionar chamadas às novas funções
- Incluir resultados nas validações
- Adicionar informações ao JSON de resposta

### 3. `frontend/app/types/analysis.ts`
**Objetivo:** Atualizar tipos TypeScript para novos campos.

**Novos campos:**
```typescript
export interface ChecklistValidacao {
  nome_arquivo_valido?: boolean
  numero_paginas?: number
  pdf_selecionavel?: boolean
  ordem_cronologica?: boolean
  abreviacoes_encontradas?: string[]
  dados_sensiveis?: string[]
  projetos_com_link?: boolean
  profile_summary_genérico?: boolean
  tech_stack_por_experiencia?: boolean
}

export interface AnalysisResult {
  // ... campos existentes
  checklist_validacao?: ChecklistValidacao
  erros_comuns_adicionais?: Array<{
    tipo: string
    descricao: string
    exemplo?: string
  }>
}
```

### 4. `frontend/app/page.tsx` e `CurriculoTool.tsx`
**Objetivo:** Exibir novas validações na UI.

**Alterações:**
- Adicionar seção "Validações do Guia"
- Exibir checklist visual (✅/❌) para cada validação
- Mostrar detalhes dos erros encontrados

---

## Implementação Passo a Passo

### Passo 1: Atualizar Prompt (knowledge/cv_analysis_prompt.md)
1. Adicionar seção "CHECKLIST COMPLETO DO GUIA"
2. Incluir todas as regras de formatação
3. Adicionar exemplos de erros comuns
4. Reforçar anti-viés para todas as áreas

### Passo 2: Adicionar Funções de Validação (backend/main.py)
1. Criar funções auxiliares para cada validação
2. Adicionar logging para debug
3. Testar cada função isoladamente

### Passo 3: Integrar no Endpoint (backend/main.py)
1. Chamar funções de validação no `analyze_cv`
2. Incluir resultados no JSON de resposta
3. Manter compatibilidade com frontend existente

### Passo 4: Atualizar Tipos (frontend/app/types/analysis.ts)
1. Adicionar novos tipos
2. Manter backward compatibility

### Passo 5: Atualizar UI (frontend/app/page.tsx, CurriculoTool.tsx)
1. Adicionar seção de checklist
2. Exibir validações visualmente
3. Mostrar sugestões de correção

### Passo 6: Testar com CVs existentes
1. Testar com todos os PDFs em `docs/`
2. Verificar se não há falsos positivos
3. Validar se novas validações funcionam

---

## Regras do Guia a Implementar

### Checklist Completo do Currículo:
- [x] Currículo está em PDF
- [x] Ctrl+F funciona no PDF (texto selecionável, não imagem)
- [x] Nome do arquivo: SeuNome_CV.pdf ou SeuNome_Resume.pdf
- [x] Apenas 1 página (até ~5 anos de exp) ou máximo 2 páginas
- [x] Design simples, sem gráficos complexos, sem barras de habilidade
- [x] Fonte preta, fundo branco, tipografia comum
- [x] Sem foto (área de engenharia não precisa)
- [x] Sem erros gramaticais ou de digitação
- [x] Experiências em ordem cronológica reversa

### Header / Contato:
- [x] Nome completo no topo
- [x] Cargo atual ou desejado
- [x] Email com link mailto: clicável
- [x] Link pro LinkedIn (URL limpa)
- [x] Link pro GitHub
- [x] Telefone com código do país (+55)
- [x] Cidade + País (ou timezone)
- [x] Endereço NÃO expõe dados sensíveis (só cidade)

### Corpo / Experiências:
- [x] Bullet points concisos
- [x] Formato XYZ ou STAR
- [x] Números e métricas
- [x] Tecnologias mencionadas
- [x] Tech stack listada por experiência
- [x] Sem abreviações (JS → JavaScript)
- [x] Sem motivo de saída
- [x] Projetos com link

### Seções Opcionais:
- [x] Profile Summary conciso
- [x] Skills/Tech Skills
- [x] Certificações
- [x] Idiomas

---

## Estrutura de Resposta (JSON)

```json
{
  "nota": 85,
  "score_ats": 78,
  "checklist_validacao": {
    "nome_arquivo_valido": true,
    "numero_paginas": 1,
    "pdf_selecionavel": true,
    "ordem_cronologica": true,
    "abreviacoes_encontradas": [],
    "dados_sensiveis": [],
    "projetos_com_link": true,
    "profile_summary_genérico": false,
    "tech_stack_por_experiencia": true
  },
  "erros_comuns_adicionais": [
    {
      "tipo": "abreviacao",
      "descricao": "JS usado em vez de JavaScript",
      "exemplo": "JS"
    }
  ],
  // ... campos existentes
}
```

---

## Testes de Validação

### Testes Unitários:
1. `_check_pdf_selectable` com PDF selecionável e imagem
2. `_count_pdf_pages` com PDFs de 1, 2, 5 páginas
3. `_detect_sensitive_data` com CPF, RG, CTPS
4. `_detect_abbreviations` com JS, HTML, CSS
5. `_check_chronological_order` com ordens correta e incorreta
6. `_check_projects_have_links` com e sem links
7. `_check_profile_summary` com genérico e específico

### Testes de Integração:
1. Upload de PDF com nome errado
2. Upload de PDF com muitos dados sensíveis
3. Upload de PDF com abreviações
4. Upload de PDF com ordem cronológica errada
5. Upload de PDF com projeto sem link
6. Upload de PDF com Profile Summary genérico

---

## Decisões

1. **Manter compatibilidade**: Todos os campos existentes devem continuar funcionando
2. **Anti-viés**: Novas validações também devem ser generéricas (não apenas dev)
3. **Performance**: Validações devem ser rápidas (< 1 segundo)
4. **Logging**: Adicionar logs para debug das validações
5. **Frontend**: UI deve mostrar status ✅/❌/⚠️ para cada validação

---

## Arquivos Criados

Nenhum novo arquivo será criado. Todas as modificações serão nos arquivos existentes.

---

## Cronograma Estimado

- Passo 1 (Prompt): 30 minutos
- Passo 2 (Funções): 1 hora
- Passo 3 (Integração): 30 minutos
- Passo 4 (Tipos): 15 minutos
- Passo 5 (UI): 1 hora
- Passo 6 (Testes): 30 minutos

**Total estimado: ~3 horas**
