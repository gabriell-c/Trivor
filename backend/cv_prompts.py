"""Prompts + colagem LLM + validadores anti-alucinação da análise de CV.

Carrega prompts de knowledge/, monta as mensagens de 2 passes, assemble do
checklist do guia e blindagens pós-LLM. Depende de cv_checks (regras puras)
e cv_extract (páginas/links do PDF). Corte de cv_helpers.py (split do god file).
"""

import json
import os
import re
import unicodedata
from pathlib import Path

from app_log import get_app_logger
from cv_checks import (
    _check_chronological_order,
    _check_profile_summary,
    _check_project_links,
    _check_tech_stack_by_experience,
    _detect_abbreviations,
    _detect_cover_letter,
    _detect_exit_reason,
    _detect_multiple_cvs,
    _detect_sensitive_data,
    _norm_text,
)
from cv_extract import _check_pdf_selectable, _count_pdf_pages

logger = get_app_logger(__name__)

# ---------------------------------------------------------------------------
# Blocos extraídos de cv_routes.analyze_cv (refatoração de complexidade):
# cópias exatas da lógica original; os _norm inline viram o _norm_text acima.
# ---------------------------------------------------------------------------

_FALLBACK_PROMPT_ESTRUT = """Você é um especialista em análise de currículos (CV) para ATS e mercado de trabalho.

REGRAS IMPORTANTES (OBRIGATÓRIO SEGUIR):
1. CAPITALIZAÇÃO: Preserve EXATAMENTE como no currículo original. Não invente capitalização.
2. BULLET POINTS: Lines starting with -, *, or • are bullet points. Preserve them.
3. DATES — REGRAS RIGOROSAS:
   - Parse dates EXACTLY as written in the CV. NEVER reformat, never invent dates.
   - If CV says "2018-2020", keep "2018-2020". If CV says "Jan 2020 - Mar 2022", keep exact text.
   - NEVER change date formats (e.g., never convert "2018" to "2018-2022" or add years).
   - NEVER interpret date ranges — only report what is literally written.
   - If no dates are present, do not invent any.
4. SPELL CHECK — REGRAS MÁXIMAMENTE RIGOROSAS:
   - SOMENTE flag palavras que estejam REALMENTE erradas segundo o dicionário português (BR).
   - NÃO flagge nomes próprios, marcas, tecnologias, abreviações, ou termos técnicos.
   - NÃO flagge erros de formatação (quebras de linha, espaçamento).
   - NÃO flagge links/URLs como erros ortográficos — links são hyperlinks válidos.
   - NÃO flagge siglas (AWS, Java, React, SQL, etc), mesmo que pareçam erradas.
   - NÃO flagge termos estrangeiros (e.g., "software", "developer", "framework").
   - Se NÃO houver erros ortográficos, retorne array vazio [].
   - WARNING: O ERRO MAIS COMUM é inventar erros que não existem. NUNCA invente.
   - Palavras como "React", "Python", "JavaScript", "AWS", "SQL" NUNCA devem ser flaggadas.
   - Nomes próprios como "São Paulo", "Maria", "João" NUNCA devem ser flagrados.
   - Antes de flaggar qualquer palavra, pergunte-se: "esta palavra REALMENTE existe no dicionário português?" Se NÃO TEM CERTEZA, NÃO flagge.
5. HYPERLINKS — REGRAS RIGOROSAS:
   - Links como wa.me, t.me, mailto:, linkedin.com, whatsapp.com são FORMATOS VÁLIDOS.
   - NÃO flagge links como "faltando https" ou "inválido".
   - Apenas reporte links na seção de links, nunca como erro.
6. NOTA (0-100):
   - "nota" deve ser ESCALA 0-100 (NÃO 0-10). Ex: 65, 78, 92.
   - "score_ats" já é 0-100 (manter).
   - Scores nas seções (analise_secoes.*) devem ser 0-100 (NÃO 0-10).
7. Be thorough and analyze EVERY line of the CV.
8. Output valid JSON only.
9. Use EXACTLY these field names (Portuguese):

{
  "nota": <0-100 float, 1 decimal>,
  "score_ats": <0-100 int>,
  "resumo_executivo": "<string>",
  "foto_detectada": <boolean>,
  "foto_recomendada": <boolean>,
  "ordem_secoes": {"correta": <boolean>, "problema": "<string|null>", "como_corrigir": "<string|null>"},
  "palavras_chave_presentes": ["<string>"],
  "palavras_chave_faltantes": ["<string>"],
  "pontos_fortes": ["<string>"],
  "pontos_fracos": ["<string>"],
  "erros_comuns_detectados": [{"tipo": "<string>", "descricao": "<string>", "exemplo": "<string|null>"}],
  "analise_secoes": {
    "dados_pessoais": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>},
    "resumo_profissional": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>},
    "experiencia_profissional": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>, "has_metrics": <boolean>},
    "formacao_academica": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>},
    "habilidades": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>, "bullet_points": <boolean>},
    "objetivo": {"status": "ok|atencao|critico", "score": <0-100>, "problema": "<string|null>", "como_corrigir": "<string|null>", "presente": <boolean>}
  },
  "analise_ats": {
    "score_ats": <0-100>,
    "palavras_chave_faltantes": ["<string>"],
    "gargalos_formatacao": ["<string>"],
    "veredito_robos": "aprovado|com_ressalvas|reprovado",
    "explicacao": "<string>"
  },
  "sugestoes": ["<string>"]
}"""

_FALLBACK_PROMPT_QUAL = ("Você é um especialista em QUALIDADE de currículos (CV). "
                         "Avalie a fórmula XYZ, a presença de métricas e a narrativa, e retorne um JSON "
                         "válido com os campos pontos_fortes e pontos_fracos. Cada item deve incluir um "
                         "trecho LITERAL do CV no formato (trecho: 'texto'); se não houver trecho que "
                         "sustente o item, omita a citação — NUNCA invente trechos nem informação.")

def _carregar_prompt_cv(caminho: Path, fallback: str) -> str:
    """Lê o prompt de analysis do knowledge/; arquivo ausente → fallback embutido."""
    if caminho.exists():
        with open(caminho, encoding='utf-8') as f:
            return f.read()
    return fallback

def _montar_checklist_guia(temp_path: str, ext: str, filename: str,
                           markdown_text: str, links_info: list,
                           logger) -> dict:
    """As 12 verificações do guia (checklist). Corpo íntegro do analyze_cv
    original — só saiu da rota para reduzir a complexidade dela."""
    checklist_validacao: dict = {}

    # 1. Verificar se PDF é selecionável
    if ext == '.pdf':
        checklist_validacao['pdf_selecionavel'] = _check_pdf_selectable(temp_path)
        checklist_validacao['numero_paginas'] = _count_pdf_pages(temp_path)
        logger.info(f"[CHECKLIST] Páginas: {checklist_validacao['numero_paginas']}")

    # 2. Verificar nome do arquivo
    nome_valido = True
    nome_problema = None
    # Padrão: NomeSobrenome_CV.pdf ou NomeSobrenome_Resume.pdf
    nome_sem_ext = os.path.splitext(filename)[0]
    if not nome_sem_ext or len(nome_sem_ext) < 3:
        nome_valido = False
        nome_problema = "Nome do arquivo muito curto ou genérico"
    elif re.match(r'^\d', nome_sem_ext):
        nome_valido = False
        nome_problema = "Nome do arquivo começa com número"
    elif '_' not in nome_sem_ext and '-' not in nome_sem_ext:
        nome_valido = False
        nome_problema = "Nome do arquivo não segue padrão Nome_Sobrenome"
    checklist_validacao['nome_arquivo'] = {
        "valido": nome_valido,
        "nome": filename,
        "problema": nome_problema
    }

    # 3. Detectar dados sensíveis
    dados_sensiveis = _detect_sensitive_data(markdown_text)
    if dados_sensiveis:
        logger.warning(f"[CHECKLIST] Dados sensíveis: {len(dados_sensiveis)} encontrados")
    checklist_validacao['dados_sensiveis'] = dados_sensiveis

    # 4. Detectar abreviações
    abreviacoes = _detect_abbreviations(markdown_text)
    if abreviacoes:
        logger.info(f"[CHECKLIST] Abreviações: {len(abreviacoes)} encontradas")
    checklist_validacao['abreviacoes'] = abreviacoes

    # 5. Verificar ordem cronológica
    ordem_check = _check_chronological_order(markdown_text)
    checklist_validacao['ordem_cronologica'] = ordem_check

    # 6. Verificar Profile Summary
    resumo_check = _check_profile_summary(markdown_text)
    checklist_validacao['profile_summary'] = resumo_check

    # 7. Verificar tecnologias por experiência
    tech_check = _check_tech_stack_by_experience(markdown_text)
    checklist_validacao['tech_stack_por_experiencia'] = tech_check

    # 8. Verificar links em projetos
    projetos_check = _check_project_links(markdown_text, links_info)
    checklist_validacao['projetos_com_link'] = projetos_check

    # 9. Verificar motivo de saída
    motivo_saida = _detect_exit_reason(markdown_text)
    if motivo_saida:
        logger.warning(f"[CHECKLIST] Motivo de saída: {len(motivo_saida)} encontrados")
    checklist_validacao['motivo_saida'] = motivo_saida

    # 10. Verificar número de páginas (punição se > 2)
    num_paginas = checklist_validacao.get('numero_paginas', 1)
    if num_paginas > 2:
        checklist_validacao['numero_paginas_valido'] = False
        checklist_validacao['numero_paginas_problema'] = f"Curriculum com {num_paginas} páginas, máximo recomendado é 2"
    else:
        checklist_validacao['numero_paginas_valido'] = True
        checklist_validacao['numero_paginas_problema'] = None

    # 11. Verificar múltiplos currículos
    multi_check = _detect_multiple_cvs(markdown_text)
    checklist_validacao['multiplos_curriculos'] = multi_check

    # 12. Verificar se é cover letter
    cover_check = _detect_cover_letter(markdown_text)
    checklist_validacao['cover_letter'] = cover_check

    logger.info(f"[CHECKLIST] Validações concluídas: {list(checklist_validacao.keys())}")
    return checklist_validacao

def _montar_mensagem_estrutura(markdown_text: str, links_info: list, ext: str,
                              extractor_used: str, job_description: str,
                              area_info: str) -> str:
    """User message do PASSO 1 (estrutura) da análise em 2 passes."""
    return (f"""ANALISE A ESTRUTURA DESTE CURRÍCULO (PASSO 1 DE 2).

CURRÍCULO (Markdown):
---
{markdown_text}
---

INFORMAÇÕES ADICIONAIS:
- Links detectados: {[link['url'] for link in links_info] if links_info else 'Nenhum'}
- Tipo de arquivo: {ext}
- Extrator usado: {extractor_used}
- Job description (se fornecida): {job_description or 'Nenhuma'}
- Target role: {area_info or 'Não especificado'}

{f'- O candidato busca posição na área de: {area_info}' if area_info else '- ÁREA DO CANDIDATO NÃO ESPECIFICADA: não assuma nenhuma área (não assuma que é tecnologia, desenvolvimento, etc.). Analise o CV de forma genérica, avaliando apenas o que está escrito.'}

Avalie APENAS o escopo deste passo (estrutura, seções, ortografia, erros comuns, ATS e checklist do guia). A crítica de qualidade (fórmula XYZ, métricas, narrativa) será feita no passo 2.""" + "\n\nESPECIFICIDADE OBRIGATÓRIA:\n- Nenhum problema pode ser genérico. Cite SEMPRE o item concreto: empresa + cargo + período para experiências ('na experiência na ACME (2023–2024), nenhum dos 3 bullets tem número mensurável'), bullet específico, seção específica. 'As experiências' sem nomear qual é proibido.\n- O campo analise_ats.explicacao deve listar, em ordem de impacto, os motivos concretos da perda de pontos que impedem score_ats de chegar a 100 (ex.: '-8: nenhuma métrica na experiência X; -5: falta a palavra-chave Y'). Se score_ats >= 90, explique em 1 linha o que ainda falta.")

def _montar_mensagem_qualidade(markdown_text: str, analysis: dict, area_info: str) -> str:
    """User message do PASSO 2 (qualidade), com o resumo do passo 1 como contexto."""
    resumo_pass1 = {
        "resumo_executivo": analysis.get("resumo_executivo"),
        "analise_secoes": analysis.get("analise_secoes"),
        "analise_ats": analysis.get("analise_ats"),
        "erros_comuns_detectados": analysis.get("erros_comuns_detectados"),
    }
    return f"""ANALISE A QUALIDADE DESTE CURRÍCULO (PASSO 2 DE 2).

CURRÍCULO (Markdown):
---
{markdown_text}
---

CONTEXTO DO PASSO 1 (análise de estrutura, JSON):
---
{json.dumps(resumo_pass1, ensure_ascii=False)[:4000]}
---

INFORMAÇÕES ADICIONAIS:
- Target role: {area_info or 'Não especificado'}

{f'- O candidato busca posição na área de: {area_info}' if area_info else '- ÁREA DO CANDIDATO NÃO ESPECIFICADA: não assuma nenhuma área (não assuma que é tecnologia, desenvolvimento, etc.). Analise a qualidade de forma genérica.'}

Avalie APENAS a qualidade (fórmula XYZ, métricas, narrativa) seguindo o prompt de sistema.
Retorne o JSON com pontos_fortes e pontos_fracos, com citações literais do currículo.

ESPECIFICIDADE OBRIGATÓRIA: cada ponto fraco que aponte uma experiência deve começar nomeando
a empresa (ou cargo + período) — ex.: 'Na experiência na ACME (2023–2024): nenhum dos 3 bullets
tem resultado mensurável (trecho: "Responsável pelo módulo de cobrança")'. Itens genéricos
('as experiências não têm métricas') são proibidos."""

def _validar_citacoes(analysis: dict, markdown_text: str) -> None:
    """VALIDAÇÃO DE CITAÇÕES (passo 2): cada trecho em (trecho: '...') tem que
    existir no texto extraído (comparação ignora acentos/maiúsculas).
    Trecho inválido → remover a citação, manter o item."""
    _norm_texto_cv = _norm_text(markdown_text)
    _citacao_pat = re.compile(
        r"\(\s*trecho\s*:\s*[\"'“”‘’]((?:(?!\s*[\"'”’]\)).)*)[\"'“”‘’]\s*\)",
        re.DOTALL,
    )
    for _campo_cit in ("pontos_fortes", "pontos_fracos"):
        if not isinstance(analysis.get(_campo_cit), list):
            continue
        def _validar_citacao(item: str) -> str:
            def _sub(m):
                trecho = m.group(1).strip()
                if trecho and _norm_text(trecho) in _norm_texto_cv:
                    return m.group(0)
                return ""
            limpo = _citacao_pat.sub(_sub, item)
            return re.sub(r'\s{2,}', ' ', limpo).strip()
        analysis[_campo_cit] = [
            s for s in (_validar_citacao(i) for i in analysis[_campo_cit] if isinstance(i, str))
            if s
        ]

def _filtrar_ortografia_grounding(analysis: dict, markdown_text: str) -> None:
    """VALIDAÇÃO DE GROUNDING: remover erros ortográficos alucinados.
    Critérios de remoção (todos devem passar para manter o erro):
    1) Palavra existe no texto extraído (ignora acentos)
    2) Palavra != correcao
    3) Palavra não é toda maiúscula (capitalização não é erro)
    4) Palavra não contém 'ç'/chars suspeitos de OCR
    5) Palavra não é acrônimo (3+ maiúsculas)"""
    extracted_norm = _norm_text(markdown_text) if markdown_text else ""
    if 'erros_ortograficos' in analysis and isinstance(analysis['erros_ortograficos'], list):
        valid_errors = []
        for err in analysis['erros_ortograficos']:
            if not isinstance(err, dict):
                continue
            word = err.get('palavra', '')
            correcao = err.get('correcao', '')

            # Critério 1: palavra deve existir no texto extraído (ignora acentos)
            if not word or _norm_text(word) not in extracted_norm:
                continue
            # Critério 2: correcao deve ser diferente da palavra
            if correcao and _norm_text(correcao) == _norm_text(word):
                continue
            # Critério 3: palavra toda em maiúsculas é capitalização, não erro
            if word == word.upper() and len(word) > 1:
                continue
            # Critério 4: palavras com 'ç' ou chars suspeitos de OCR → ignorar
            if 'ç' in word or 'ñ' in word or any(ord(c) > 127 and c not in 'áéíóúâêîôûãõéèêëïîôùÿáàâéèêëïîôùÿ' for c in word):
                continue
            # Critério 5: acrônimos (3+ letras maiúsculas) → ignorar
            if len(word) >= 3 and word.isupper():
                continue
            valid_errors.append(err)
        analysis['erros_ortograficos'] = valid_errors

def _blindar_falsos_positivos(analysis: dict, markdown_text: str, area_info: str) -> None:
    """PÓS-PROCESSAMENTO DEFINITIVO: blindar a saída do LLM contra falsos
    positivos de ortografia (critérios A-J), viés dev quando a área não foi
    informada, erros comuns de capitalização/OCR e inconsistência narrativa.
    Mutates analysis in place — mesma semântica do bloco original da rota."""
    # Normalização sem remover acentos — só lowercase + normalizaçao NFD
    def _norm_accent(s: str) -> str:
        return unicodedata.normalize('NFD', s).lower()

    # Extrair TODAS as palavras do texto extraído (tokenização por espaço+pontuação)
    _words_raw = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", markdown_text or "")
    _words_norm = {_norm_text(w) for w in _words_raw}

    # 1) ERRORS ORTOGRÁFICOS: validação rigorosa em nível de palavra
    if 'erros_ortograficos' in analysis and isinstance(analysis['erros_ortograficos'], list):
        valid_errors = []
        for err in analysis['erros_ortograficos']:
            if not isinstance(err, dict):
                continue
            word = err.get('palavra', '')
            correcao = err.get('correcao', '')
            contexto = err.get('contexto', '')

            # A) Palavra precisa existir como token isolado no texto extraído
            if not word or _norm_text(word) not in _words_norm:
                continue
            # B) Correcao não pode ser igual à palavra (comparação exata, não normalizada)
            if correcao and _norm_accent(correcao) == _norm_accent(word):
                continue
            # C) Tudo maiúsculo: só ignorar se a forma lowercase existir no texto extraído
            #    (ex: "API" é sigla correta, mas "REDUSEI" não existe mesmo em lowercase)
            if word == word.upper() and len(word) > 1:
                # Verificar se a versão lowercase existe no texto como palavra correta
                word_lower = word.lower()
                if _norm_text(word_lower) in _words_norm:
                    continue  # palavra existe no texto em lowercase → é capitalização, não erro
                # Se não existe no texto, pode ser erro ortográfico mesmo em caps
                # (ex: "REDUSEI" → lowercase "redusei" não existe → erro real)
            # D) Chars suspeitos de OCR → ignorar
            if 'ç' in word or 'ñ' in word:
                continue
            # E) Acrônimos 3+ letras que existem no texto → ignorar
            if len(word) >= 3 and word.isupper():
                word_lower = word.lower()
                if _norm_text(word_lower) in _words_norm:
                    continue
                # Se não existe no texto, pode ser erro (ex: "REDUSEI" em caps)
            # F) Correcao = word.upper() → é capitalização, não erro ortográfico
            if correcao and correcao == word.upper():
                continue
            # G) Palavra lowercase + correcao uppercase = capitalização, não erro
            if word.islower() and correcao and correcao.isupper():
                continue
            # H) Contexto NÃO pode conter palavras inexistentes no texto extraído
            ctx_words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", contexto or '')
            if ctx_words and not all(_norm_text(x) in _words_norm for x in ctx_words):
                continue
            # I) Correção NÃO pode conter palavras inexistentes
            if correcao:
                corr_words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", correcao)
                if corr_words and not all(_norm_text(x) in _words_norm for x in corr_words):
                    continue
            # J) Palavra não pode ser duas palavras juntas (ex: "seguran ca" → artefato OCR)
            if ' ' in word or '\n' in word or '-' in word:
                continue
            valid_errors.append(err)
        analysis['erros_ortograficos'] = valid_errors

    # 2) Quando área NÃO é especificada: blindagem total contra viés dev
    if not area_info:
        analysis['palavras_chave_faltantes'] = []
        if 'ordem_secoes' in analysis:
            analysis['ordem_secoes']['correta'] = True
            analysis['ordem_secoes']['problema'] = None
            analysis['ordem_secoes']['como_corrigir'] = None
        # Palavras-chave que indicam viés de tech/dev
        dev_keywords = {
            'linguagem', 'linguagen', 'linguagens', 'framework', 'frameworks',
            'tech', 'tecnologia', 'tecnologias', 'api', 'apis',
            'banco de dados', 'database', 'sql',
            'javascript', 'typescript', 'python', 'java', 'c++', 'c#', 'csharp',
            'react', 'angular', 'vue', 'node', 'nodejs', 'dev',
            'desenvolvimento', 'desenvolver', 'programação', 'programar',
            'código', 'codigos', 'software', 'frontend', 'backend', 'fullstack',
            'git', 'github', 'gitlab', 'aws', 'azure', 'docker', 'kubernetes',
            'k8s', 'ci/cd', 'pipeline', 'agile', 'scrum', 'sprint',
            'biblioteca', 'bibliotecas', 'scripts', 'script',
            'computador', 'computação', 'ti', 't.i.', 'informática',
        }
        if 'pontos_fracos' in analysis and isinstance(analysis['pontos_fracos'], list):
            analysis['pontos_fracos'] = [
                pf for pf in analysis['pontos_fracos']
                if not any(kw in pf.lower() for kw in dev_keywords)
            ]
        # Se ainda sobrou algum ponto fraco com viés tech, zerar
        if any(any(kw in pf.lower() for kw in dev_keywords) for pf in analysis.get('pontos_fracos', [])):
            analysis['pontos_fracos'] = []
        # Filtrar resumo_executivo: remover apenas menções a FALTA de skills tech
        if 'resumo_executivo' in analysis and isinstance(analysis['resumo_executivo'], str):
            # Só filtrar se o resumo mencionar falta/déficit de competências tech
            missing_tech_pattern = re.compile(
                r'(falta|ausência|deveria ter|precisa|deveria possuir|lucro|ganho|vantagem).*(linguagem|framework|tech|tecnolog|api|sql|git|aws|docker|react|node|python|java|frontend|backend|fullstack|programa|código|script)',
                re.IGNORECASE
            )
            sentences = re.split(r'(?<=[.!?])\s+', analysis['resumo_executivo'])
            cleaned = [s for s in sentences if not missing_tech_pattern.search(s)]
            if len(cleaned) < len(sentences):
                analysis['resumo_executivo'] = ' '.join(cleaned)
                analysis['resumo_executivo'] = re.sub(r'\s+', ' ', analysis['resumo_executivo']).strip()

    # 3) ERROS COMUNS DETECTADOS: filtrar capitalização e OCR
    if 'erros_comuns_detectados' in analysis and isinstance(analysis['erros_comuns_detectados'], list):
        valid_comuns = []
        for err in analysis['erros_comuns_detectados']:
            if not isinstance(err, dict):
                continue
            descricao = err.get('descricao', '')
            exemplo = err.get('exemplo', '')
            tipo = err.get('tipo', '').lower()
            # Remover se exemplo não existe no texto
            if exemplo and _norm_text(exemplo) not in _words_norm:
                continue
            # Remover se exemplo contém chars de OCR
            if 'ç' in (exemplo or '') or 'ñ' in (exemplo or ''):
                continue
            # Remover se tipo/descrição é sobre capitalização (várias variações)
            desc_lower = descricao.lower()
            if (tipo in ('capitalizacao', 'capitalização', 'capitalization', 'uppercase', 'maiúscula', 'maiscula')
                or 'capitaliz' in desc_lower
                or 'maiúscula' in desc_lower
                or 'maiscula' in desc_lower
                or 'uppercase' in desc_lower
                or 'maiúscul' in desc_lower
                or 'maiúsc' in desc_lower):
                continue
            # Remover se erro é sobre capitalização: palavra + correção = mesma palavra em cases diferentes
            # Remove se erro é sobre capitalização: exemplo + correção = mesma palavra em cases diferentes
            # (usa os campos do PRÓPRIO erro comum — nunca variáveis de outro loop)
            correcao_comum = (err.get('correcao') or '').strip()
            if correcao_comum and exemplo and exemplo.lower() == correcao_comum.lower() and exemplo != correcao_comum:
                continue
            # Remover se exemplo é toda maiúscula e a versão lowercase existe no texto
            if exemplo and exemplo == exemplo.upper() and len(exemplo) > 1:
                if _norm_text(exemplo.lower()) in _words_norm:
                    continue
            valid_comuns.append(err)
        analysis['erros_comuns_detectados'] = valid_comuns

    # 4) CONSISTÊNCIA NARRATIVA: se não há erros ortográficos, remover pontos fracos que alegam erros ortográficos
    has_spelling_errors = bool(analysis.get('erros_ortograficos'))
    spelling_pattern = re.compile(
        r'erro[s]? ortográfic[os]?|erros? de ortografia|erros? gramaticais|ortograf[icose]?|deslizes? ortográfic[os]?|erros? de digita[çc][ao]|erros? de escrita|digitacao|ajuste[s]? ortográfic[os]?|corre[çc][ao]es? ortográfic[as]?',
        re.IGNORECASE
    )
    if 'pontos_fracos' in analysis and isinstance(analysis['pontos_fracos'], list) and not has_spelling_errors:
        analysis['pontos_fracos'] = [
            pf for pf in analysis['pontos_fracos']
            if not spelling_pattern.search(pf)
        ]
        # Remover pontos fracos que mencionam artefatos de OCR (ç, ñ, espaços quebrados)
        ocr_pattern = re.compile(r'segurançe|artefato[zs]? de extra[çc][ao]|artefato[s]? OCR|quebra[s]? de linha|formata[çc][ao]', re.IGNORECASE)
        analysis['pontos_fracos'] = [
            pf for pf in analysis['pontos_fracos']
            if not ocr_pattern.search(pf)
        ]
    # Filtrar resumo_executivo: remover menções a erros ortográficos se não há erros reais
    if 'resumo_executivo' in analysis and isinstance(analysis['resumo_executivo'], str) and not has_spelling_errors:
        # Remover frases inteiras que mencionam erro ortográfico
        sentences = re.split(r'(?<=[.!?])\s+', analysis['resumo_executivo'])
        cleaned = [s for s in sentences if not spelling_pattern.search(s)]
        analysis['resumo_executivo'] = ' '.join(cleaned)
        # Limpeza final
        analysis['resumo_executivo'] = re.sub(r'\s+', ' ', analysis['resumo_executivo']).strip()
        analysis['resumo_executivo'] = re.sub(r'([.,;:!])\s*\1+', r'\1', analysis['resumo_executivo'])
