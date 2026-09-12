# Plano: Corrigir Extração e Volume de Vagas Administrativas

## Problemas Identificados

### Problema 1 — Volume baixo (~72 vagas, ~29 utilizáveis)
- JSearch API retorna ~12 vagas por query (num_pages ignorado)
- 10 queries sequenciais com 0.5s sleep = ~120 vagas teóricas
- Pré-filtro + IA rejeitam muitas vagas
- **Causa raiz**: queries sequenciais lentas + possível filtro agressivo

### Problema 2 — Descarte sem motivo exibido
- `rejection_reason` existe no DB mas IA nem sempre preenche
- Prompt pede mas não FORÇA o preenchimento
- **Causa**: prompt fraco na regra de rejection_reason

### Problema 3 — Poucos skills extraídos (Word, experiência, ensino superior, PowerPoint)
- De 39 vagas administrativas: só 2 pedem Word, 2 experiência, 2 ensino superior, 1 PowerPoint
- **Causa raiz**: IA não extrai skills administrativos comuns
- Fallback heurístico nunca dispara: condição `len(requirements) < 2` mas IA sempre retorna ≥2
- `_sanitize_requirements` tem `_SKILL_MAX_LEN = 50` que pode filtrar termos legítimos longos

### Problema 4 — Poucos nice_to_have (diferenciais)
- IA não separa bem "obrigatório" vs "desejável" em vagas administrativas

---

## Análise do Código

### Normalização (já existe, verificar cobertura)
- `market_service.py` linhas 82-91: patterns para Excel, Word, PowerPoint já existem
- `r"\bpacote\s+office\b"` → "Excel" (linha 82) — CORRETO, agrupa Pacote Office com Excel
- `r"\bword\b"` → "Word" (linha 89) — já existe
- `r"\b(powerpoint|ms\s*powerpoint|microsoft\s+powerpoint)\b"` → "PowerPoint" (linha 91)

### Fallback heurístico (linha 1639)
- Condição: `len(result.get("requirements", [])) < 2`
- **PROBLEMA**: IA sempre retorna ≥2 requirements (mesmo que ruins), então fallback NUNCA dispara
- A heurística que extrai "Word", "Excel", "Ensino Médio" do texto nunca é usada

### Sanitização (linha 1393)
- `_SKILL_MAX_LEN = 50` — filtra termos > 50 chars
- "Experiência na área administrativa de compras (a partir de 1 ano)" = 62 chars → filtrado ✓ (era lixo)
- Mas "Formação cursando ou concluído em qualquer área" = 50 chars → limite justo
- **Problema potencial**: termos legítimos de 45-50 chars podem ser borderline

### Prompt de extração (linha 1669)
- Já tem exemplos de ferramentas, idiomas, formação
- Mas não tem exemplos ESPECÍFICOS de vagas administrativas
- Não forza rejection_reason com exemplo de formato

---

## Mudanças Propostas

### 1. Melhorar prompt de extração — foco em vagas administrativas
**Arquivo**: `market_service.py` (~linha 1669)

Adicionar ao prompt:
- Exemplos concretos de extração para vagas administrativas
- Reforçar: "Para vagas administrativas, SEMPRE extraia: Word, Excel, Pacote Office, Digitação, Inglês/Português, Ensino Médio/Superior"
- Forçar rejection_reason com exemplo: `"rejection_reason": "cargo diferente — vaga de vendedor, não administrativo"`

### 2. Tornar fallback heurístico mais agressivo
**Arquivo**: `market_service.py` (~linha 1639)

Alterar condição de fallback:
- De: `len(result.get("requirements", [])) < 2`
- Para: também disparar se `len(result.get("requirements", [])) < 5` E a vaga contém palavras-chave administrativas ("administrativo", "assistente", "vaga", "clerical", "escritório")

### 3. Adicionar heurística pós-extração (safety net)
**Arquivo**: `market_service.py` (nova função após `_sanitize_requirements`)

Criar `_ensure_common_skills(item, job_text)` que:
- Roda DEPOIS da extração da IA e do sanitize
- Verifica se o job_text contém skills administrativos comuns
- Se SIM e NÃO estão nos requirements extraídos, adiciona
- Skills a verificar: Word, Excel, Pacote Office, Informática, Digitação, Inglês, Português, Ensino Médio, Ensino Superior, Orientação a detalhes

### 4. Aumentar volume com parallel queries
**Arquivo**: `market_service.py` (~linha 744)

Substituir loop sequencial por `concurrent.futures.ThreadPoolExecutor`:
- 3 threads simultâneas
- Cada thread processa 3-4 queries
- Manter dedup e sleep entre batches

### 5. Corrigir _SKILL_MAX_LEN no sanitize
**Arquivo**: `market_service.py` (~linha 1393)

Aumentar de 50 para 80 caracteres para permitir termos legítimos como:
- "Experiência na área administrativa" (38 chars) — já passa
- "Conhecimento em legislação trabalhista" (41 chars) — já passa
- Termos mais longos como "Formação superior completa em qualquer área" (50 chars) — borderline
- Aumentar para 80 dá margem segura

---

## Ordem de Implementação

1. **Corrigir `_SKILL_MAX_LEN`** (50→80) — risco mínimo
2. **Melhorar prompt de extração** — impacto direto
3. **Adicionar `_ensure_common_skills()`** — safety net para admin
4. ** Tornar fallback heurístico mais agressivo** — cobre falhas da IA
5. **Parallel queries** — aumenta volume
6. **Forçar rejection_reason no prompt** — corrige UX

---

## Arquivos a Modificar

| Arquivo | Alteração | Linha aprox. |
|---------|-----------|-------------|
| `backend/market_service.py` | `_SKILL_MAX_LEN` 50→80 | 1393 |
| `backend/market_service.py` | Prompt de extração (admin examples + rejection_reason force) | 1669-1743 |
| `backend/market_service.py` | Nova função `_ensure_common_skills()` | após 1488 |
| `backend/market_service.py` | Chamar `_ensure_common_skills` no pipeline | ~1886 |
| `backend/market_service.py` | Fallback heurístico mais agressivo | 1639 |
| `backend/market_service.py` | Parallel queries com ThreadPoolExecutor | 744-762 |
| `backend/market_service.py` | Import `concurrent.futures` | topo |

---

## Verificação

Após implementação:
1. Executar análise de "assistente administrativo"
2. Verificar se Word/Excel aparecem em 15+ vagas (não só 2)
3. Verificar se ensino superior/experiência são extraídos corretamente
4. Verificar se Nice-to-have tem mais itens
5. Verificar se volume de vagas aumenta (>100 raw, >50 relevantes)
6. Verificar se motivos de descarte aparecem para todas as vagas descartadas
