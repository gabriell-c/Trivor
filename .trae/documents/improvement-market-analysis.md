# Plano: Melhorar Análise de Mercado — Prompt da IA + UI

## Resumo
Corrigir a classificação de dados pela IA (benefícios/modalidades não são skills) e melhorar a exibição UI (tooltip em textos truncados + mais soft skills).

---

## Problemas Identificados

### 1. Prompt de extração — classificação errada
- **Arquivo**: `backend/market_service.py` linhas 796-820 (e 893-945)
- **Problema**: O prompt pede "requirements: Extraia TUDO que a vaga exige" de forma genérica. A IA interpreta benefícios (Auxílio Educação, Plano de Saúde) e modalidades (Home Office) como requisitos.
- **Causa raiz**: Não há distinção clara entre categories (skills técnicas, soft skills, benefícios, modalidades, certificações). O prompt não dá exemplos negativos.

### 2. Soft skills limitadas a 5 itens
- **Arquivo**: `backend/market_service.py` linha 1223
- **Problema**: `[:5]` corta artificialmente a lista de soft skills e certificações.

### 3. Textos truncados sem tooltip
- **Arquivo**: `frontend/app/market/page.tsx` linhas 395, 427, 458
- **Problema**: `w-32 truncate` corta nomes longos sem forma de ver o texto completo.

---

## Alterações Propostas

### Arquivo 1: `backend/market_service.py`

#### A. Melhorar prompt `extract_job_with_ai` (linha ~796)
- Adicionar seções de classificação clara com exemplos positivos E negativos
- Instruir explicitamente: NÃO colocar benefícios, modalidades, salários em `requirements`
- Dizer que `requirements` = apenas skills técnicas/ferramentas/idiomas/formação
- Expandir `soft_skills` com mais exemplos e regras (ex: "trabalho em equipe" conta, "home office" não conta)
- Aumentar limit de soft skills extraídas por vaga de 4 para 10

#### B. Melhorar prompt `classify_and_extract` (linha ~893)
- Aplicar as mesmas melhorias do prompt acima
- Garantir consistência entre os dois prompts

#### C. Remover limite de 5 soft skills e certificações (linha 1222-1227)
- Trocar `[:5]` por `[:15]` para ambos (soft skills e certificações)
- Justificativa: com 20+ vagas analisadas, far sentido mostrar mais itens

#### D. Aumentar limite de soft skills por vaga no mock (linha ~180)
- Trocar `random.randint(2, min(4, ...))` por `random.randint(2, min(8, ...))`
- Justificativa: vagas reais têm mais soft skills listadas

### Arquivo 2: `frontend/app/market/page.tsx`

#### A. Adicionar tooltip nos nomes truncados
- Linhas 395 e 427: mudar `w-32 truncate` para um container com `title` attribute (tooltip nativo do browser)
- Ou usar tooltip visual com Tailwind (group-hover)
- Linha 458: mesma abordagem para modalidades

---

## Arquivos para modificar
1. `backend/market_service.py` — prompts + limites
2. `frontend/app/market/page.tsx` — tooltip nos nomes truncados

---

## Decisões
- Não criar lista fixa de palavras (conforme pedido do usuário) — apenas melhorar o prompt com exemplos e regras de classificação
- Aumentar soft skills de 5 para 15 no agregador
- Tooltip nativo (`title` attribute) é suficiente — não precisa de biblioteca adicional

## Verificação
1. Rodar análise de mercado com uma query real
2. Confirmar que "Auxílio Educação", "Plano de Saúde", "Home Office" NÃO aparecem em required_technologies
3. Confirmar que soft skills tem mais de 5 itens
4. Confirmar que textos longos mostram tooltip ao passar o mouse
