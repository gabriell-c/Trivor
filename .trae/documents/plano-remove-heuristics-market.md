# Plano: Remover todas as heurísticas/fabricação de dados na Inteligência de Mercado

## Resumo
Eliminar os fallbacks heurísticos que inventam dados quando a IA falha. Se a IA não consegue analisar uma vaga, ela simplesmente não entra nos resultados — sem fabricação, sem substituição por regex, sem sobreposição de decisões.

---

## Análise do Estado Atual

Foram identificados **3 pontos de fabricação de dados** no fluxo de análise de mercado:

### 1. `heuristic_extract` (linha 471-474)
Marca vagas como `is_relevant: True` com dados vazios só porque o texto tem >100 caracteres:
```python
# Se nada foi extraído mas o texto é substancial, marcar como relevante com dados mínimos
if len(job_text) > 100 and not result["requirements"] and not result["role_level"]:
    result["is_relevant"] = True
```

### 2. `extract_job_with_ai` (linha 708-710)
Quando a IA falha, cai em `heuristic_extract` que inventa dados por regex:
```python
except Exception as e:
    logger.warning(f"[WARN] extract_job_with_ai fallback to heuristic: {e}")
    return heuristic_extract(job_text)
```

### 3. `run_market_analysis` (linha 1115-1119)
Quando a IA marca uma vaga como irrelevante, mas a heurística diz o contrário, o sistema **ignora a IA e força como relevante**:
```python
# Se a IA marcou como irrelevante mas a heurística diz o contrário, confia na heurística
if not is_rel and extracted.get("requirements"):
    is_rel = is_relevant_heuristic(job_text, stack_list, seniority, location)
    if is_rel:
        extracted["is_relevant"] = True
```

### 4. Mensagem de log enganosa (linha 1004-1006)
`_pad_missing_jobs` apenas truncava resultados, mas o log dizia "Completing missing jobs with heuristics" (enganoso).

---

## Mudanças Propostas

### Arquivo: `backend/market_service.py`

#### Alteração 1 — Linha 471-474: Remover marcação automática de relevância no `heuristic_extract`
**O que:** Remover o bloco que força `is_relevant = True` em textos longos sem dados extraídos.
**Por quê:** Texto longo sem conteúdo estruturado não deve ser considerado relevante.

```python
# ANTES:
# Se nada foi extraído mas o texto é substancial, marcar como relevante com dados mínimos
if len(job_text) > 100 and not result["requirements"] and not result["role_level"]:
    result["is_relevant"] = True

# DEPOIS:
# (removido — texto longo sem dados não é relevante)
```

#### Alteração 2 — Linha 707-710: Remover fallback heurístico no `extract_job_with_ai`
**O que:** Quando a IA falha, retornar `{}` (dicionário vazio) ao invés de chamar `heuristic_extract`.
**Por quê:** Dicionário vazio fará com que a vaga seja tratada como sem dados válidos e simplesmente ignorada no processamento posterior.

```python
# ANTES:
except Exception as e:
    logger.warning(f"[WARN] extract_job_with_ai fallback to heuristic: {e}")
    return heuristic_extract(job_text)

# DEPOIS:
except Exception as e:
    logger.warning(f"[WARN] extract_job_with_ai falhou, vaga ignorada: {e}")
    return {}
```

#### Alteração 3 — Linha 1115-1119: Remover override de relevância por heurística no loop principal
**O que:** Remover o bloco que substitui a decisão da IA pela heurística.
**Por quê:** A IA é a autoridade. Se ela disse que não é relevante, não é.

```python
# ANTES:
# Se a IA marcou como irrelevante mas a heurística diz o contrário, confia na heurística
if not is_rel and extracted.get("requirements"):
    is_rel = is_relevant_heuristic(job_text, stack_list, seniority, location)
    if is_rel:
        extracted["is_relevant"] = True

# DEPOIS:
# (removido — a decisão da IA é definitiva)
```

#### Alteração 4 — Linha 1004-1006: Corrigir mensagem de log enganosa
**O que:** Trocar "Completing missing jobs with heuristics" por mensagem precisa.
**Por quê:** `_pad_missing_jobs` não completa com heurística — apenas truncava.

```python
# ANTES:
logger.warning(
    f"[WARN] batch size mismatch: parsed {len(data)} jobs from {len(job_texts)}. "
    f"Completing missing jobs with heuristics."
)

# DEPOIS:
logger.warning(
    f"[WARN] batch size mismatch: parsed {len(data)} jobs from {len(job_texts)}. "
    f"Jobs ausentes serão ignorados (sem dados fabricados)."
)
```

---

## Arquivos a modificar
- `backend/market_service.py` — 4 alterações pontuais (remover/reformular linhas ~471, ~708, ~1115, ~1004)

## Funções que ficam mortas (não mais chamadas)
- `heuristic_extract` — ainda existe no arquivo, mas não será mais invocada pelo fluxo principal. Pode ser removida posteriormente se desejado.
- `is_relevant_heuristic` — também perde o único uso no loop principal.

---

## Suposições e Decisões
- O `_pad_missing_jobs` (linha 873) já faz a coisa certa (retorna apenas dados reais, truncando), então só corrigimos o log.
- `_fallback_extract_jobs` (linha 893) já é OK — chama `extract_job_with_ai` individualmente, e agora que a linha 708 retorna `{}` em vez de heurística, o fallback também não fabricará dados.
- `heuristic_extract` e `is_relevant_heuristic` permanecem no arquivo por enquanto (código morto) — não serão removidas para evitar risco de quebrar algo sem necessidade. Se quiser limpeza completa, é fazer depois.

---

## Verificação
1. Rodar `py main.py` e confirmar que não há SyntaxError
2. Rodar uma análise de mercado com job title qualquer
3. Verificar no log que:
   - Não aparecem warnings de "fallback to heuristic"
   - Vagas que a IA não processa simplesmente não aparecem nos resultados
   - Nenhum dado fabricado (reqs vazios, soft_skills vazios) aparece como "relevante"
4. Verificar que a análise funciona normalmente quando a IA responde corretamente
