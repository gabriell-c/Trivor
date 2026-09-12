# Plano: Correção da Qualidade de Busca — Inteligência de Mercado

## Resumo do Problema

Ao pesquisar "Assistente Administrativo" com filtro **Remoto Nacional**, o sistema retornou:
- Vagas em espanhol ("Agendador De Citas Telefonicas, Trabajo Remoto")
- Vagas de Porto Rico ("Curitiba, Puerto Rico")
- Vagas do Reino Unido ("Londres, Angleterre")
- Vagas da Holanda ("Snåsa, Trøndelag")
- Vagas não relacionadas (biotech, data operations, seguros)

**Causa raiz**: O filtro de país e o detector de nacionalidade são insuficientes. A JSearch API com `country=br` retorna vagas de Puerto Rico, EUA e outros países marcadas como "BR" no campo `job_country`, mas com localização física em outro lugar.

---

## Análise do Estado Atual

### 1. Filtro de país em `_fetch_jsearch_jobs` (linha 172-177)
```python
# ATUAL — só confia no campo job_country da API
filtered_raw = [
    j for j in raw_jobs
    if (j.get("job_country") or "").lower() in ("br", "brazil", "brasil")
]
```
**Problema**: A JSearch marca Puerto Rico como "BR". Vagas de Porto Rico passam.

### 2. Detecção de nacionalidade em `detect_job_nationality` (linha 673)
```python
# ATUAL — só detecta USD/English como internacional
if c in ("br", "brazil", "brasil"): return "nacional"
if c not in ("", None): return "internacional"
```
**Problema**: "Puerto Rico" tem `job_country="BR"`, então é classificado como "nacional". Vagas em espanhol passam.

### 3. Pré-filtro em `_pre_filter_jobs` (linha 766)
- Não verifica a string de localização (`job_location`)
- Não verifica idioma do texto
- O fallback permissivo (linha 831) adiciona TODAS as vagas brutas se o filtro zerar

### 4. Queries de busca (linha 378-389)
- Falta query com exclusão de territórios não-BR
- Falta query mais específica com termos brasileiros

---

## Mudanças Propostas

### Alteração 1: `_fetch_jsearch_jobs` — Rejeitar vagas de locais não-BR

**Arquivo**: `backend/market_service.py`
**Onde**: Função `_fetch_jsearch_jobs`, após linha 176

**O quê**: Adicionar verificação do campo `job_location` da API para rejeitar vagas de territórios não-BR.

**Como**:
```python
if expected == "br":
    filtered_raw = []
    for j in raw_jobs:
        jc = (j.get("job_country") or "").lower()
        jl = (j.get("job_location") or "").lower()
        # Aceita se country=BR E location não indica território estranho
        if jc in ("br", "brazil", "brasil"):
            # Rejeita se location contém termos de territórios não-BR
            skip_terms = ["puerto rico", "pr ", "puerto", "usa", "united states",
                          "united kingdom", "uk ", "inglaterra", "londres",
                          "holanda", "netherlands", "mexico", "espanha", "españa",
                          "canadá", "canada", "portugal", "frança", "france"]
            if not any(t in jl for t in skip_terms):
                filtered_raw.append(j)
```

### Alteração 2: `detect_job_nationality` — Detectar idiomas e países não-BR

**Arquivo**: `backend/market_service.py`
**Onde**: Função `detect_job_nationality`, antes do return "nacional" (linha 715)

**O quê**: Adicionar detecção de idiomas estrangeiros e países não-BR no texto.

**Como**: Adicionar dois novos blocos de verificação antes do default:

```python
# --- Detecção por idioma no título/descrição ---
lang_signals = {
    "spanish": ["español", "espanol", "trabajo", "agendador", "atención",
                "representante", "servicio", "ventas", "seguros", "licencia",
                "oportunidad", "buscamos", "agente", "auxiliar", "concesiones"],
    "dutch": ["raadgever", "alreial", "milieu", "natuur", "vilt", "kulturskolerådet"],
    "french": "francais",
    "english_strong": ["english required", "bilingual", "native english"],
}
for lang, signals in lang_signals.items():
    if lang == "english_strong":
        continue  # já tratado acima
    if isinstance(signals, list):
        if any(s in text_lower for s in signals):
            # Verifica se NÃO é português
            pt_signals = ["assistente", "administrativo", "vaga", "clt",
                          "remoto", "brasile", "brasil", "salario",
                          "departamento", "pessoal", "atendimento",
                          "cliente", "comercial", "licenciatura"]
            if not any(p in text_lower for p in pt_signals):
                return "internacional"

# --- Detecção por país na localização ---
loc_country_signals = [
    "puerto rico", "pr ", "usa", "united states",
    "united kingdom", "uk ", "inglaterra", "londres",
    "holanda", "netherlands", "mexico", "espanha",
    "canadá", "canada", "portugal", "frança", "france",
    "são tomé", "são tomé e príncipe", "timor-leste",
]
for sig in loc_country_signals:
    if sig in text_lower:
        return "internacional"
```

### Alteração 3: `_pre_filter_jobs` — Verificar string de localização

**Arquivo**: `backend/market_service.py`
**Onde**: Função `_pre_filter_jobs`, após a detecção de nacionalidade (linha 813)

**O quê**: Adicionar verificação explícita da localização para rejeitar cidades/países não-BR.

**Como**: Adicionar após a verificação de nationality (linha 813):
```python
# LOCALIZAÇÃO — rejeita vagas com localização física fora do Brasil
if is_nacional:
    loc_text = (loc + " " + description).lower()
    non_br_locations = [
        "puerto rico", "puerto", "pr,", "pr ",
        "united states", "usa,", "usa ",
        "united kingdom", "uk,", "uk ", "londres", "inglaterra",
        "netherlands", "holanda", "mexico", "espanha",
        "canadá", "canada", "portugal", "frança",
        "trøndelag", "snåsa", "san german",
    ]
    if any(l in loc_text for l in non_br_locations):
        continue
```

### Alteração 4: Queries de busca — Mais específicas

**Arquivo**: `backend/market_service.py`
**Onde**: Função `generate_mock_jobs_if_empty`, seção de queries (linha 378)

**O quê**: Adicionar queries com exclusão de territórios e mais termos brasileiros.

**Como**: Substituir as queries existentes (linhas 378-389) por:
```python
queries = []
if geo_keywords:
    queries.append(f"{search_query} {geo_keywords[0]}")
queries.append(search_query)

port_translation = _translate_to_portuguese(search_query)
if port_translation:
    queries.append(port_translation)
    if geo_keywords:
        queries.append(f"{port_translation} {geo_keywords[0]}")

queries.append(f"{search_query} vaga brasil")
queries.append(f"{search_query} remoto brasil")
queries.append(f"{search_query} clt")
queries.append(f"{search_query} emprego brasil")
```

### Alteração 5: Fallback menos permissivo

**Arquivo**: `backend/market_service.py`
**Onde**: Função `_pre_filter_jobs`, linha 831-836

**O quê**: O fallback deve aplicar o mesmo filtro de localização/idioma, não adicionar todas as vagas brutas.

**Como**:
```python
if not filtered and raw_jobs:
    logger.warning(f"[MARKET] Pré-filtro descartou todas as {len(raw_jobs)} vagas — aplicando fallback com filtro de localização")
    for j in raw_jobs[:max_jobs]:
        job_id, title, company, description, loc, mod, source, source_url = j
        # Re-aplica filtro básico de localização mesmo no fallback
        job_text_lower = (title + " " + description).lower()
        skip = False
        for l in ["puerto rico", "puerto", "united kingdom", "londres",
                   "netherlands", "holanda", "mexico", "espanha",
                   "canadá", "portugal", "frança"]:
            if l in job_text_lower:
                skip = True
                break
        if skip:
            continue
        job_text = f"Título: {title}\nEmpresa: {company}\nLocalização: {loc}\nModalidade: {mod}\nDescrição:\n{description}"
        filtered.append((1, job_id, title, company, description, loc, mod, source, source_url, job_text))
```

---

## Arquivos Modificados

| Arquivo | Linhas | Alteração |
|---|---|---|
| `backend/market_service.py` | ~172-177 | Filtro de país com verificação de location |
| `backend/market_service.py` | ~673-715 | Detecção de idioma e país no texto |
| `backend/market_service.py` | ~813 | Verificação de localização no pré-filtro |
| `backend/market_service.py` | ~378-389 | Queries mais específicas |
| `backend/market_service.py` | ~831-836 | Fallback com filtro de localização |

---

## Assunções

1. A JSearch API retorna `job_location` com a localização completa (cidade, estado, país)
2. A JSearch API retorna `job_country` com código ISO (BR, US, PR, etc.)
3. Vagas 100% remotas sem localização física serão aceitas (não há como saber o país)
4. O usuário quer apenas vagas do Brasil para "Remoto Nacional"

---

## Verificação

1. Buscar "Assistente Administrativo" com "Remoto Nacional" → não deve retornar vagas de Puerto Rico, UK, Holanda
2. Buscar "Assistente Administrativo" com "Remoto Nacional" → não deve retornar vagas em espanhol
3. Buscar "Python Developer" com "Remoto Nacional" → deve retornar vagas BR
4. Buscar "Software Engineer" com "Remoto Internacional" → deve retornar vagas US/Internacionais
5. Verificar logs: nenhuma vaga com "puerto rico", "londres", "netherlands" no resultado final
