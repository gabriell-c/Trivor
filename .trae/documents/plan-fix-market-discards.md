# Plan: Fix Market Analysis Job Discarding and Add Rejection Reasons

## Problem

1. **Too many jobs discarded without reason**: When searching "Assistente Administrativo" with "remoto nacional" filter and NO negative keywords, many valid Brazilian jobs are discarded by the AI relevance check (is_relevant=false). The user sees "Relevant: 45" out of "Jobs scanned: 146" — 101 jobs discarded with no explanation.

2. **No rejection reasons shown**: The UI doesn't display why any job was discarded. The user can't understand what's being filtered out.

## Root Cause Analysis

The AI extraction prompt tells the model: "is_relevant=TRUE se o cargo for compatível com o perfil do usuário" with a vague profile. The AI is being overly strict — classifying valid Brazilian admin jobs as irrelevant because the AI doesn't understand that "Assistente Administrativo" with "remoto nacional" should match ANY administrative role in Brazil.

Additionally, the `_pre_filter_jobs` already does geography/nationality filtering (correctly rejecting international jobs), but the AI then discards even MORE valid national jobs.

## Changes Required

### 1. Fix AI prompt to be less strict on relevance (market_service.py)
**File**: `backend/market_service.py`
**Lines**: ~1251-1296 (extract_jobs_batched prompt)

Change the RELEVÂNCIA section from:
```
RELEVÂNCIA: is_relevant=TRUE se o cargo for compatível com o perfil do usuário. Vagas remotas são SEMPRE relevantes.
Perfil: cargo={job_title_context}, stack={...}, seniority={seniority}, location={location}
```
To something more permissive:
```
RELEVÂNCIA: is_relevant=TRUE se:
- O cargo corresponder ao título buscado (mesma função ou similar)
- A vaga for do Brasil (nacional)
- NÃO houver palavras negativas na descrição
is_relevant=FALSE APENAS se:
- A vaga for de outro país/idioma
- O cargo for completamente diferente (ex: vendedor quando buscava engenheiro)
- Houver termo negativo na descrição
Vagas remotas/nacionais do cargo buscado são SEMPRE relevantes.
```

### 2. Add rejection_reason to extracted results (market_service.py)
**File**: `backend/market_service.py`
**Lines**: ~1284-1296 (batch prompt format)

Add `"rejection_reason": "string|null"` to the JSON schema, and add instructions:
```
Se is_relevant=false, explique brevemente o motivo em rejection_reason (max 30 chars).
```

### 3. Store rejection reasons in the data (market_service.py)
**File**: `backend/market_service.py`
**Lines**: ~1471-1492 (extracted_jobs array)

Add `"rejection_reason"` to each job object in extracted_jobs, including for relevant jobs (null).

### 4. Pass rejection reasons to frontend (market_service.py)
**File**: `backend/market_service.py`
**Lines**: ~1586-1630 (report_result construction)

Include rejection reasons in the summary or as a separate field in sample_jobs.

### 5. Display rejection reasons in frontend (frontend/app/market/page.tsx)
**File**: `frontend/app/market/page.tsx`
**What**: Show rejection reasons when jobs are filtered/discarded. Add a info panel or tooltip showing why jobs were rejected.

### 6. Reduce AI batch size or increase fallback coverage
**File**: `backend/market_service.py`
**What**: Ensure the fallback path (`_fallback_extract_jobs`) properly handles all cases. Also make `heuristic_extract` set `is_relevant=True` for jobs that pass the pre-filter (since pre-filter already did nationality/geography checks).

## Verification Steps

1. Run `python test_quick.py` — all 7 tests pass
2. Run full E2E test: `python test_final.py` — expect more relevant jobs (aim for 80%+)
3. Check that `rejection_reason` field appears in API response
4. Verify frontend shows rejection info
