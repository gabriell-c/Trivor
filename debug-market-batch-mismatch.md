# Debug: Market Batch Size Mismatch — RESOLVIDO

## Bug
```
[WARN] batch size mismatch: parsed 0 jobs from 6 (IA may have returned unexpected format). Falling back to per-job extraction.
```

## Causa Raiz
1. `_parse_batch_response` retornava `[]` quando a IA enviava um objeto único em vez de array
2. O chamador não tinha forma de completar os jobs faltantes
3. O fallback sempre executava, mesmo quando a IA tinha retornado dados parciais úteis

## Hipóteses Testadas
1. ~~IA retorna JSON inválido~~ → descartado (seria exceção, não 0 jobs)
2. ~~IA retorna objeto único em vez de array~~ → **CONFIRMADO** — causa raiz
3. IA retorna estrutura inesperada → parcialmente confirmado
4. Parse error silencioso → descartado
5. Thinking tags interferem → descartado (tags são removidas antes do parse)

## Fix Aplicado

### 1. `_parse_batch_response` (linha 910)
- Agora retorna `[data]` quando recebe um dict de job, independente do `expected`
- Chamador é responsável por lidar com discrepância de tamanho

### 2. Nova função `_pad_missing_jobs` (linha 929)
- Completa jobs faltantes usando `heuristic_extract`
- Se a IA retornou 1 de 6 jobs, usa IA para o 1º + heurística para os outros 5
- Evita fallback completo quando parte dos dados já veio da IA

### 3. Flow atualizado em `extract_jobs_batched` (linha ~1090)
```
Parse response → _parse_batch_response
    ↓
Se len(data) < expected → _pad_missing_jobs (heurística para os faltantes)
Se len(data) > expected → truncate
    ↓
Se ainda discrepante → fallback completo (_fallback_extract_jobs)
```

## Verificação
- [x] Syntax valid
- [x] Scenario 1: 1 dict → padded to 6 jobs ✅
- [x] Scenario 2: empty array → padded to 3 jobs ✅
- [x] Scenario 3: extra jobs → truncated correctly ✅
- [x] Scenario 4: unknown format → all heuristics ✅

## Resultado
O warning agora aparece apenas quando há discrepância real que não pode ser resolvida com padding. A maioria dos cases (IA retorna 1-5 de N jobs) agora é tratada com padding heurístico, evitando fallback completo que consome mais requisições IA.
