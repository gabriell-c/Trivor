"""Busca de vagas reais via JSearch API + geração de amostra para a base.

Agrega resultados de múltiplas chaves (retry distribuído por subconjunto de
chaves), deduplica por job_id e preenche market_raw_jobs quando a base está
vazia. Se JSearch não retornar nada (sem chave/falha), a base fica vazia —
nenhum dado é fabricado.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from market_db import _connect_market_db, _mask_jsearch_key, _update_jsearch_usage
from market_keywords import sanitize
from market_log import logger

_JSEARCH_API_URL = "https://api.openwebninja.com/jsearch/search-v2"
_JSEARCH_HEADERS = {
    "X-API-Key": "",  # Placeholder, definido em runtime
    "Accept": "application/json",
}

# Minimum delay between API calls per key (seconds)
_JSEARCH_MIN_DELAY = 0.5

# Delay between parallel batches (seconds)
_BATCH_DELAY = 0.8

# Delay when all keys are rate-limited (seconds)
_RATE_LIMIT_ALL_SLEEP = 15.0

# Max retry attempts for rate-limited queries
_MAX_RETRY = 2
_RETRY_BASE_DELAY = 3.0


def _parse_jsearch_posted_at(raw) -> str:
    """Converte job_date_posted (API JSearch) para ISO. Ausente/inválido → None (caller usa fallback)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for cand in (s, s.replace("Z", "+00:00"), s.replace("/", "-")):
        try:
            return datetime.fromisoformat(cand).isoformat()
        except ValueError:
            continue
    logger.debug(f"[JSearch] job_date_posted em formato não suportado: {raw!r} — usando data atual")
    return None


def _fetch_jsearch_jobs(
    query: str,
    country: str = "br",
    language: str = "pt",
    num_pages: int = 4,
    api_keys: list[str] | None = None,
    date_posted: str = "all",
) -> tuple:
    """Através JSearch API busca vagas reais, agregando resultados de TODAS as chaves."""
    if not api_keys:
        return [], None, None

    params = urllib.parse.quote_plus(query)
    url_template = f"{_JSEARCH_API_URL}?query={params}&country={country}&language={language}&num_pages={num_pages}&date_posted={date_posted}"

    all_raw_jobs = []
    last_remaining = None
    last_total = None
    keys_tried = []
    rate_limited_keys = set()  # chaves que já retornaram 429 nesta sessão

    for api_key in api_keys:
        api_key = api_key.strip()
        if not api_key:
            continue

        if api_key in rate_limited_keys:
            logger.debug(f"[JSearch] Pulando chave {_mask_jsearch_key(api_key)} (rate-limited nesta sessão)")
            continue
        keys_tried.append(api_key)
        req = urllib.request.Request(url_template, headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("status") == "OK":
                raw_jobs = data.get("data", {}).get("jobs", [])
                remaining = resp.headers.get("x-ratelimit-remaining")
                total = resp.headers.get("x-ratelimit-limit")
                logger.info(f"[JSearch] Chave {_mask_jsearch_key(api_key)} → {len(raw_jobs)} vagas | rate: {remaining}/{total}")
                # Filtra vagas pelo país esperado — chaves diferentes podem retornar países errados
                expected = country.lower()
                if expected == "br":
                    # Para Brasil: aceita BR explícito, mas rejeita localizações de territórios não-BR
                    # (JSearch marca Puerto Rico como BR, mas localização é PR)
                    # NOTE: não rejeita jobs com job_country vazio — pode ser vaga BR sem país definido
                    _SKIP_LOC_TERMS = {
                        "puerto rico", "puerto ", " pr,", " pr ",
                        "united states", "usa,", "usa ",
                        "united kingdom", "uk,", "uk ", "inglaterra", "londres",
                        "netherlands", "holanda", "mexico", "espanha", "españa",
                        "canadá", "canada", "portugal", "frança", "france",
                        "trøndelag", "snåsa", "san german", "são tomé",
                    }
                    filtered_raw = []
                    for j in raw_jobs:
                        jc = (j.get("job_country") or "").lower()
                        jl = (j.get("job_location") or "").lower()
                        # Aceita se país for BR explícito
                        if jc in ("br", "brazil", "brasil"):
                            filtered_raw.append(j)
                            continue
                        # Rejeita se país for explicitamente não-BR
                        if jc and jc not in ("", "usa", "united states"):
                            continue
                        # Rejeita se localização contém termo de território não-BR
                        if any(t in jl for t in _SKIP_LOC_TERMS):
                            continue
                        # Aceita: país vago ou não-BR mas localização compatível
                        filtered_raw.append(j)
                else:
                    # Para internacional: aceita US explícito ou vago (remoto global)
                    filtered_raw = [
                        j for j in raw_jobs
                        if (j.get("job_country") or "").lower() in (expected, "usa", "united states", "")
                    ]
                skipped = len(raw_jobs) - len(filtered_raw)
                if skipped > 0:
                    logger.warning(f"[JSearch] Chave {_mask_jsearch_key(api_key)} filtrou {skipped} vagas de país errado ({expected})")
                all_raw_jobs.extend(filtered_raw)
                last_remaining = int(remaining) if remaining else last_remaining
                last_total = int(total) if total else last_total
            else:
                logger.warning(f"[JSearch] Chave {_mask_jsearch_key(api_key)} retornou erro: {data.get('message', 'unknown')}")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.warning(f"[JSearch] Chave {_mask_jsearch_key(api_key)} 403 (sem créditos ou inválida), tentando próxima...")
                rate_limited_keys.add(api_key)
                continue
            elif e.code == 429:
                logger.warning(f"[JSearch] Chave {_mask_jsearch_key(api_key)} 429 (rate limit)")
                rate_limited_keys.add(api_key)
                continue
            else:
                logger.error(f"[JSearch] HTTP erro {e.code}: {e.reason}")
                continue
        except Exception as e:
            logger.error(f"[JSearch] Erro com chave {_mask_jsearch_key(api_key)}: {e}")
            continue
        # Throttle between key attempts to avoid IP rate limit
        time.sleep(max(0.5, _JSEARCH_MIN_DELAY))

    # If ALL keys were rate-limited, wait longer before next query
    if len(rate_limited_keys) >= len(api_keys) and api_keys:
        logger.warning(f"[JSearch] Todas as {len(api_keys)} chaves rate-limited. Aguardando {_RATE_LIMIT_ALL_SLEEP}s...")
        time.sleep(_RATE_LIMIT_ALL_SLEEP)

    jobs = _build_jobs_from_raw(all_raw_jobs, country)
    logger.info(f"[JSearch] Query {query!r}: {len(jobs)} vagas agregadas de {len(keys_tried)} chave(s)")
    return jobs, last_remaining, last_total


def _build_jobs_from_raw(raw_jobs: list, default_country: str) -> list[dict]:
    """Constrói lista de jobs a partir dos dados brutos da API."""
    jobs = []
    for j in raw_jobs:
        # Extrai link de candidatura (prioriza job_apply_link, depois apply_options)
        apply_link = j.get("job_apply_link", "")
        if not apply_link and j.get("apply_options"):
            apply_link = j["apply_options"][0].get("apply_link", "")

        # Extrai informações de salário
        salary = j.get("job_salary", "")

        # Extrai destaques da descrição
        highlights = j.get("job_highlights", {})
        highlights_text = ""
        if isinstance(highlights, dict):
            highlights_text = " ".join(
                f"{k}: {', '.join(v)}" for k, v in highlights.items() if v
            )

        # Monta descrição completa
        desc_parts = []
        if j.get("job_description"):
            desc_parts.append(j["job_description"])
        if highlights_text:
            desc_parts.append(highlights_text)
        if salary:
            desc_parts.append(f"Salário: {salary}")
        description = " ".join(desc_parts)

        # Cidade/Estado/País
        city = j.get("job_city", "")
        state = j.get("job_state", "")
        job_country = j.get("job_country", default_country)
        if city and state:
            location = f"{city}, {state}"
        elif city:
            location = city
        else:
            location = job_country if job_country else default_country

        # Tipo de emprego
        emp_type = j.get("job_employment_type", "")
        if emp_type == "FULLTIME":
            modality = "Presencial"
        elif emp_type == "PARTTIME":
            modality = "Meio período"
        elif j.get("job_city") == "" and j.get("job_state") == "":
            modality = "Remoto"
        else:
            modality = emp_type or "Presencial"

        # Fonte
        publisher = j.get("job_publisher", "JSearch")

        jobs.append({
            "title": j.get("job_title", "Unknown"),
            "company": j.get("employer_name", "Unknown"),
            "description": description,
            "location": location,
            "modality": modality,
            "source": publisher,
            "source_url": apply_link,
            "seniority": "",
            "job_id": j.get("job_id", ""),
            "job_country": job_country,
            "published_at": j.get("job_date_posted", ""),
        })
    return jobs


def _get_jsearch_country_language(location: str) -> tuple:
    """Retorna (country, language) baseado na seleção de localização do usuário."""
    loc = location.lower()
    if "internacional" in loc:
        return "us", "en"
    return "br", "pt"


def _get_geo_keywords(location: str) -> list[str]:
    """Retorna palavras-chave geográficas para enriquecer as queries de busca."""
    loc = location.lower()
    if "internacional" in loc:
        # Busca internacional roda em inglês (country=us, language=en) → keywords em inglês, não do Brasil
        return ["remote", "global", "international", "work from anywhere"]
    return ["Brasil", "Brazil", "remoto Brasil", "vaga Brasil"]


def generate_mock_jobs_if_empty(db_file: Path, job_title: str = "Desenvolvedor Backend", jsearch_api_keys: list[str] | None = None, date_posted: str = "all", location: str = "Remoto Nacional"):
    """Preenche a base de vagas quando está vazia.
    Se jsearch_api_keys (lista) for fornecido, tenta buscar vagas reais primeiro
    (com JSEARCH_API_KEY do ambiente como chave sintética extra).
    Usa múltiplas queries para maximizar o volume de vagas.
    Se JSearch não retornar nada (sem chave/falha), a base fica vazia —
    nenhum dado é fabricado.
    """
    conn = _connect_market_db(db_file)
    count = conn.execute("SELECT COUNT(*) FROM market_raw_jobs").fetchone()[0]
    # Não segura a conexão aberta durante a fase HTTP (minutos) — WAL + busy_timeout
    # cuidam da concorrência; a conexão só reabre para os INSERTs
    conn.close()

    if count == 0:
        env_key = os.getenv("JSEARCH_API_KEY", "").strip()

        # Primeiro tenta JSearch com as chaves fornecidas (fallback automático)
        sample_jobs = []
        used_key_remaining = None
        valid_keys = [k.strip() for k in (jsearch_api_keys or []) if k and k.strip()]
        if env_key and env_key not in valid_keys:
            valid_keys.append(env_key)  # chave sintética do ambiente (id="env")
        if jsearch_api_keys or env_key:
            if valid_keys:
                search_query = job_title.strip()
                country, language = _get_jsearch_country_language(location)
                geo_keywords = _get_geo_keywords(location)

                # ATENÇÃO: Queries massivas para maximizar volume → 200+ vagas relevantes
                # Cada query com num_pages=12 retorna ~144 vagas; 30 queries = ~4320 vagas brutas
                queries = []

                # Query principal com geo
                if geo_keywords:
                    queries.append(f"{search_query} {geo_keywords[0]}")
                queries.append(search_query)

                # Termos brasileiros essenciais
                queries.append(f"{search_query} vaga brasil")
                queries.append(f"{search_query} emprego brasil")
                queries.append(f"{search_query} remoto brasil")
                queries.append(f"{search_query} clt")
                queries.append(f"{search_query} contratação")
                queries.append(f"{search_query} home office")
                queries.append(f"{search_query} online")

                # Plataformas (geram vagas diferentes)
                queries.append(f"{search_query} linkedin")
                queries.append(f"{search_query} catho")
                queries.append(f"{search_query} infojobs")
                queries.append(f"{search_query} glassdoor")

                # Níveis de experiência
                queries.append(f"{search_query} junior")
                queries.append(f"{search_query} pleno")
                queries.append(f"{search_query} estagiario")
                queries.append(f"{search_query} entry level")

                # Regiões e indústria
                queries.append(f"{search_query} sao paulo")
                queries.append(f"{search_query} sudeste brasil")
                queries.append(f"{search_query} banca")

                # Queries em paralelo: execução em 6 lotes concorrentes, cada um com um subconjunto de chaves distinto
                all_jobs = {}
                from concurrent.futures import ThreadPoolExecutor, as_completed

                def _fetch_single_query(q, keys_subset=None, date_posted="month"):
                    """Executa uma query; aceita um subconjunto de chaves para distribuir a pressão de IP."""
                    keys = keys_subset if keys_subset else valid_keys
                    return _fetch_jsearch_jobs(q, country=country, language=language,
                                               num_pages=12, api_keys=keys, date_posted=date_posted)

                # Divide as chaves válidas em 6 subconjuntos, o mais uniformemente possível
                def _split_keys(keys, n):
                    """Divide a lista de chaves em n sublistas, o mais uniforme possível."""
                    if not keys:
                        return [[] for _ in range(n)]
                    result = [[] for _ in range(n)]
                    for i, k in enumerate(keys):
                        result[i % n].append(k)
                    return result

                key_subsets = _split_keys(valid_keys, 6)

                batch_size = 6
                max_concurrent = min(batch_size, len(valid_keys)) if valid_keys else 1
                total_batches = (len(queries) + batch_size - 1) // batch_size

                # Conta o número de queries bem-sucedidas/falhas por lote, para o retry posterior
                failed_queries = []  # Registra as queries que retornaram 0 resultados
                max_retries = _MAX_RETRY

                for batch_idx in range(total_batches):
                    batch_queries = queries[batch_idx * batch_size : (batch_idx + 1) * batch_size]
                    # Cada query recebe um subconjunto de chaves distinto (deslocamento round-robin)

                    with ThreadPoolExecutor(max_workers=min(len(batch_queries), max_concurrent)) as executor:
                        futures = {}
                        for i, q in enumerate(batch_queries):
                            # Cada query usa um subconjunto de chaves com deslocamento próprio, para distribuir ainda mais a pressão de IP
                            inner_offset = (batch_idx + i) % len(key_subsets)
                            inner_subset = key_subsets[inner_offset]
                            futures[executor.submit(_fetch_single_query, q, inner_subset)] = q

                        for future in as_completed(futures):
                            q = futures[future]
                            try:
                                jobs, rem, _ = future.result()
                            except Exception as e:
                                logger.error(f"[MARKET] Query {q!r} falhou: {e}")
                                jobs = []
                                rem = None
                            logger.info(f"[MARKET] JSearch query {q!r}: {len(jobs)} vagas")
                            dup_before = len(all_jobs)
                            for j in jobs:
                                # Dedup: prioriza job_id da API, fallback para hash título+empresa+local
                                raw_jid = j.get("job_id", "")
                                if raw_jid:
                                    dedup_key = f"api:{raw_jid}"
                                else:
                                    dedup_key = hashlib.md5(
                                        f"{j.get('title','')}|{j.get('company','')}|{j.get('location','')}"
                                        .encode()).hexdigest()
                                all_jobs[dedup_key] = j
                            logger.info(f"[MARKET] Query {q!r}: {len(jobs)} novas, {len(all_jobs)-dup_before} únicas")
                            if rem is not None and valid_keys:
                                used_key_remaining = rem
                            # Registra a query falha (0 resultados) para o retry posterior
                            if len(jobs) == 0:
                                failed_queries.append(q)

                    # Atraso entre lotes: evita rate limit de nível de IP
                    time.sleep(_BATCH_DELAY)

                # Lógica de retry: repete as queries que retornaram 0 resultados, cada vez com um subconjunto de chaves diferente
                for retry_attempt in range(1, max_retries + 1):
                    if not failed_queries:
                        break
                    logger.info(f"[MARKET] Retry attempt {retry_attempt}: {len(failed_queries)} queries failed, waiting {_RETRY_BASE_DELAY * retry_attempt}s")
                    time.sleep(_RETRY_BASE_DELAY * retry_attempt)
                    still_failed = []
                    for q in failed_queries:
                        subset_offset = (retry_attempt + failed_queries.index(q)) % len(key_subsets)
                        subset = key_subsets[subset_offset]
                        try:
                            jobs, rem, _ = _fetch_jsearch_jobs(q, country=country, language=language,
                                                                  num_pages=6, api_keys=subset, date_posted=date_posted)
                        except Exception as e:
                            logger.error(f"[MARKET] Retry query {q!r} falhou: {e}")
                            jobs = []
                            rem = None
                        logger.info(f"[MARKET] Retry {retry_attempt} query {q!r}: {len(jobs)} vagas")
                        dup_before = len(all_jobs)
                        for j in jobs:
                            raw_jid = j.get("job_id", "")
                            if raw_jid:
                                dedup_key = f"api:{raw_jid}"
                            else:
                                dedup_key = hashlib.md5(
                                    f"{j.get('title','')}|{j.get('company','')}|{j.get('location','')}"
                                    .encode()).hexdigest()
                            all_jobs[dedup_key] = j
                        logger.info(f"[MARKET] Retry {retry_attempt} query {q!r}: {len(jobs)} novas, {len(all_jobs)-dup_before} únicas")
                        if rem is not None and valid_keys:
                            used_key_remaining = rem
                        if len(jobs) == 0:
                            still_failed.append(q)
                    failed_queries = still_failed
                    if not still_failed:
                        break

                sample_jobs = list(all_jobs.values())
                retry_note = f"com {len(failed_queries)} queries ainda falhas" if failed_queries else "sem retry necessário"
                logger.info(f"[MARKET] JSearch combinou {len(sample_jobs)} vagas únicas de {len(queries)} queries, {retry_note}")
                # Atualiza uso no DB
                if used_key_remaining is not None and valid_keys:
                    _update_jsearch_usage(db_file, valid_keys[0], used_key_remaining)

        # Se JSearch falhou ou não configurado, prossegue com lista vazia (sem dados fabricados)
        if not sample_jobs:
            logger.info("[MARKET] JSearch sem resultados ou não configurado — prosseguindo com 0 vagas reais")

        if sample_jobs:
            conn = _connect_market_db(db_file)  # reabre APENAS p/ os INSERTs
            try:
                cursor = conn.cursor()
                now = datetime.now()
                for j in sample_jobs:
                    job_id = str(uuid.uuid4())
                    # published_at real da API (job_date_posted); fallback: agora —
                    # sem a progressão artificial de 3 dias por posição
                    pub_date = _parse_jsearch_posted_at(j.get("published_at")) or now.isoformat()
                    source_url = j.get("source_url", "")
                    job_country = j.get("job_country", "")
                    # Anexa país como metadado na descrição para uso posterior no filtro
                    if job_country:
                        country_meta = f"\n[PAÍS: {job_country.upper()}]"
                        desc = j["description"] + country_meta
                    else:
                        desc = j["description"]
                    cursor.execute('''
                        INSERT INTO market_raw_jobs (id, title, company, description, location, modality, source, source_url, published_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (job_id, sanitize(j["title"]), sanitize(j["company"]), sanitize(desc), sanitize(j["location"]), sanitize(j["modality"]), sanitize(j["source"]), source_url, pub_date))
                conn.commit()
            finally:
                conn.close()
