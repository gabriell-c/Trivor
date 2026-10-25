"""Contexto único de perfil para os LLMs dos bots de candidatura.

Todos os bots (gupy, infojobs, solides, indeed, nedin) injetam o texto
gerado por `contexto_perfil()` nos prompts — assim a IA enxerga TODAS as
informações que o usuário mantém na aba Perfil do Trivor
(config.yaml + apply/.env), em um só bloco, com regras explícitas de como
responder. Em especial a lista negativa (`busca.palavras_excluir`): se a
pergunta for sobre Java e "java" estiver na lista, a IA responde NÃO /
"Nenhum" — e nunca apresenta o candidato como se soubesse.

Módulo puro (stdlib) — pode ser importado do backend e dos testes sem
puxar a camada de browser de `common`.
"""
import os
import re
from collections.abc import Mapping
from datetime import date, datetime

# Chaves de documento que o contexto lê do .env (mesma allowlist dos bots;
# senhas/credenciais NUNCA entram no prompt).
ENV_DOC_KEYS = (
    'CANDIDATO_CPF', 'CANDIDATO_RG', 'CANDIDATO_CNH',
    'CANDIDATO_NOME_PAI', 'CANDIDATO_NOME_MAE', 'CANDIDATO_NACIONALIDADE',
)

# Endereços do .env sobrepõem o config.yaml nos bots — o contexto espelha a regra.
# campo do config → chave do .env
_ENV_ENDERECO_OVERRIDES = {
    'logradouro': 'ENDERECO_LOGRADOURO',
    'numero': 'ENDERECO_NUMERO',
    'complemento': 'ENDERECO_COMPLEMENTO',
    'bairro': 'ENDERECO_BAIRRO',
    'cep': 'ENDERECO_CEP',
    'cidade': 'ENDERECO_CIDADE',
    'estado': 'ENDERECO_ESTADO',
}


def _valor(fonte: Mapping[str, str], chave: str) -> str:
    v = fonte.get(chave, '')
    return (v or '').strip() if isinstance(v, str) else str(v).strip()


def _doc(env: Mapping[str, str] | None, chave: str) -> str:
    """Documento do .env — `env` explícito (backend/teste) ou os.environ
    (o bot já fez load_dotenv no import)."""
    fonte = env if env is not None else os.environ
    return _valor(fonte, chave)


def linhas_do_config(config: dict, campo: str, padrao: list[str] | None = None) -> list[str]:
    """Campo de config como lista de linhas (UI grava cada linha do textarea
    como um item). Tolerante a string com \\n em vez de lista."""
    valor = (config.get('candidato') or {}).get(campo, padrao if padrao is not None else [])
    if isinstance(valor, str):
        valor = valor.splitlines()
    return [linha.strip() for linha in valor if isinstance(linha, str) and linha.strip()]


def tech_excluida(tech: str, negativas: list[str]) -> bool:
    """Decide se uma tecnologia da pergunta cai na lista negativa.

    Fronteira de palavra: "java" exclui "Java" e "Java SE", mas NÃO exclui
    "JavaScript" (o próximo caractere é letra). Também casa tokens internos:
    "aws (amazon web services)" é excluído por "aws".
    """
    t = re.sub(r'\s+', ' ', (tech or '').strip().lower())
    if not t:
        return False
    for n in negativas or []:
        nn = re.sub(r'\s+', ' ', (n or '').strip().lower())
        if not nn:
            continue
        if t == nn:
            return True
        if t.startswith(nn):
            resto = t[len(nn):]
            if not resto or not resto[0].isalpha():
                return True
        if nn in re.findall(r'[a-z0-9.+#]+', t):
            return True
    return False


def titulo_excluido(titulo: str, negativas: list[str]) -> str | None:
    """Decide se um título de vaga (ou texto de card) cai na lista negativa,
    com fronteira de palavra: "java" exclui "Analista Java" mas NÃO exclui
    "Analista Javascript". Retorna a palavra que excluiu (para log) ou None.

    Os filtros de vaga de TODOS os bots passam por aqui — uma mudança na
    semântica vale para os 5 provedores de uma vez.
    """
    t = re.sub(r'\s+', ' ', (titulo or '').lower())
    for n in negativas or []:
        nn = re.sub(r'\s+', ' ', (n or '').strip().lower())
        if not nn:
            continue
        # (?<!\w)/(?!\w) em vez de \b: fronteira no caractere de "palavra",
        # e acentuados contam (ex.: "sênior" casa com "Analista sênior")
        if re.search(r'(?<!\w)' + re.escape(nn) + r'(?!\w)', t):
            return n
    return None


def _idade(config: dict) -> str:
    bruto = str((config.get('candidato') or {}).get('data_nascimento') or '').strip()
    if not bruto:
        return ''
    # A UI grava DD/MM/AAAA (o Sólides faz strptime rígido nesse formato);
    # aceita ISO por tolerância.
    nasc = None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            nasc = datetime.strptime(bruto, fmt).date()
            break
        except ValueError:
            continue
    if nasc is None:
        return ''
    hoje = date.today()
    idade = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
    return f"{idade} anos (nascido em {bruto})"


def _lista_negativa(config: dict) -> list[str]:
    busca = config.get('busca') or {}
    valor = busca.get('palavras_excluir') or []
    if isinstance(valor, str):
        valor = valor.splitlines()
    return [str(x).strip() for x in valor if str(x).strip()]


def contexto_perfil(config: dict, env: Mapping[str, str] | None = None) -> str:
    """Monta o bloco de contexto (PT-BR) que os prompts dos bots recebem.

    - `config` = config.yaml inteiro; `env` = chaves do apply/.env (os.environ
      quando None). Seções vazias viram "(não informado)" — nunca cortam a
    regra que a IA precisa enxergar (exclusões, pretensões, disponibilidade).
    """
    c = config.get('candidato') or {}
    div = config.get('diversidade') or {}
    loc = config.get('localizacao') or {}
    end = config.get('endereco') or {}
    negativas = _lista_negativa(config)
    idade = _idade(config)

    def s(chave: str, padrao: str = '') -> str:
        v = c.get(chave)
        return str(v).strip() if v not in (None, '') else padrao

    def end_valor(campo: str) -> str:
        base = str(end.get(campo) or '').strip()
        override = _ENV_ENDERECO_OVERRIDES.get(campo)
        if override:
            v = _doc(env, override)
            if v:
                return v
        return base

    def bool_simnao(valor) -> str:
        return 'SIM' if valor else 'NÃO'

    def blocos_linhas(rotulo: str, itens: list[str]) -> str:
        if not itens:
            return f"{rotulo}:\n  (não informado)"
        return f"{rotulo}:\n" + "\n".join(f"  - {i}" for i in itens)

    form = c.get('formacao')
    form = form if isinstance(form, dict) else {}
    form_linhas = []
    if form.get('curso'):
        situacao = str(form.get('situacao') or '').strip()
        form_linhas.append(f"  - {form['curso']}"
                           + (f" — {form.get('instituicao')}" if form.get('instituicao') else '')
                           + (f" ({situacao})" if situacao else '')
                           + (f", conclusão {form.get('ano_conclusao')}" if form.get('ano_conclusao') else ''))
    techs = config.get('tecnologias') or {}
    tech_linhas = "\n".join(f"  - {n}: {v}" for n, v in techs.items()) or "  (não informado)"
    idiomas = linhas_do_config(config, 'idiomas')
    # inglês do config já entra na lista; evita duplicata na seção de idiomas
    nivel_ingles = s('nivel_ingles')

    partes: list[str] = []

    partes.append("════ IDENTIDADE ════")
    partes.append(f"Nome: {s('nome', '(não informado)')}")
    if idade:
        partes.append(f"Idade: {idade}")
    nac = _doc(env, 'CANDIDATO_NACIONALIDADE')
    if nac:
        partes.append(f"Nacionalidade: {nac} — autorizado a trabalhar no Brasil")
    for rotulo, chave in (("CPF", 'CANDIDATO_CPF'), ("RG", 'CANDIDATO_RG'), ("CNH", 'CANDIDATO_CNH')):
        v = _doc(env, chave)
        partes.append(f"{rotulo}: {v if v else 'NÃO possui / não informado'}")
    pai = _doc(env, 'CANDIDATO_NOME_PAI')
    mae = _doc(env, 'CANDIDATO_NOME_MAE')
    partes.append(f"Pai: {pai if pai else 'não informado'} — Mãe: {mae if mae else 'não informado'}")

    partes.append("\n════ CONTATO & LINKS ════")
    partes.append(f"E-mail: {s('email', '(não informado)')}")
    partes.append(f"Telefone: {s('telefone', '(não informado)')} — Cidade: {s('cidade_uf', '(não informado)')}")
    partes.append(f"LinkedIn: {s('linkedin', '(não informado)')} — GitHub: {s('github', '(não informado)')}"
                  f" — Portfólio: {s('portfolio', '(não informado)')}")

    partes.append("\n════ ENDEREÇO (o bloco .env tem prioridade) ════")
    partes.append(" — ".join(x for x in [
        end_valor('logradouro'), end_valor('numero'), end_valor('complemento'),
        end_valor('bairro'), end_valor('cep'), end_valor('cidade'), end_valor('estado'),
    ] if x))
    partes.append(f"País: {str(end.get('pais') or '').strip() or 'Brasil'}")

    partes.append("\n════ FORMAÇÃO & EXPERIÊNCIA ════")
    partes.append(blocos_linhas("Formação", form_linhas) if form_linhas
                   else "Formação:\n  (não informado)")
    partes.append(blocos_linhas("Cursos & Certificações", linhas_do_config(config, 'certificacoes')))
    partes.append(blocos_linhas("Experiência & Projetos", linhas_do_config(config, 'experiencia')))
    sobre = s('sobre')
    if sobre:
        partes.append(f"Sobre si (para perguntas abertas): {sobre}")

    partes.append("\n════ TECNOLOGIAS (experiência real) ════")
    partes.append(tech_linhas)

    partes.append("\n════ LISTA DE EXCLUSÕES (respostas obrigatórias) ════")
    if negativas:
        partes.append("Itens excluídos pelo candidato: " + ", ".join(negativas))
        partes.append(
            "REGRAS — aplique sempre que a pergunta tocare nesses itens:\n"
            "  • \"Você sabe/usou Java?\" (ou qualquer item da lista) → responda NÃO / \"não tenho experiência\".\n"
            "  • Nível de experiência por tecnologia: item da lista → \"Nenhum\" / \"0 anos\" / opção mais baixa.\n"
            "  • Nunca cite esses itens como habilidade sua em textos (apresentação, carta, respostas).\n"
            "  • Itens de senioridade/anos na lista (ex.: sênior, 5/8/10 anos) → nunca se apresente nesse nível.\n"
            "  • Vaga que pede EXCLUSIVAMENTE algo da lista → responda honestamente que não atende; "
            "é melhor não candidatar do que responder errado.")
    else:
        partes.append("(lista vazia — sem exclusões configuradas)")

    partes.append("\n════ IDIOMAS ════")
    if nivel_ingles:
        partes.append(f"  - Inglês: {nivel_ingles}")
    for i in idiomas:
        if i.split(':', 1)[0].strip().lower() != 'inglês':
            partes.append(f"  - {i}")
    if not idiomas and not nivel_ingles:
        partes.append("  (não informado)")

    partes.append("\n════ PRETENSÕES & DISPOIBILIDADE ════")
    partes.append(
        f"CLT: R$ {s('pretensao_clt', '(não informado)')}/mês — PJ hora: R$ {s('pretensao_pj_hora', '(—)')}"
        f" — PJ mensal: R$ {s('pretensao_pj_mensal', '(—)')} — Estágio: R$ {s('pretensao_estagio', '(—)')}/mês")
    partes.append(
        f"Início: {s('inicio', 'Imediata')} — Carga horária: {s('horas_semana', '(não informado)')}"
        f" — Dias por semana: {s('disponibilidade_dias', '(não informado)')}"
        f" — Possui empresa aberta (PJ): {'SIM' if c.get('possui_pj') else 'NÃO'}")
    partes.append(
        "REGRA CRÍTICA DE PRETENSÃO: pergunta com PJ/hora → valor PJ; com CLT/carteira → valor CLT; "
        "sem regime → CLT. NUNCA revelar salário atual/último (pular o campo).")

    partes.append("\n════ LOCALIZAÇÃO & FORMATO DE TRABALHO ════")
    partes.append(
        f"Remoto: {bool_simnao(loc.get('aceita_remoto'))} — Híbrido: {bool_simnao(loc.get('aceita_hibrido'))}"
        f" — Presencial: {bool_simnao(loc.get('aceita_presencial'))}"
        f" — Aceita mudança: {bool_simnao(loc.get('aceita_mudanca'))}")
    partes.append(f"Estados aceitos: {', '.join(loc.get('estados_aceitos') or ['(todos)'])}")

    partes.append("\n════ DIVERSIDADE & INCLUSÃO ════")
    partes.append(
        f"Raça/Cor: {div.get('raca_cor') or '(não informado)'!s}"
        f" — Gênero: {div.get('genero') or '(não informado)'!s}"
        f" — Orientação: {div.get('orientacao_sexual') or '(não informado)'!s}"
        f" — PCD: {'SIM' if div.get('pcd') else 'NÃO'}"
        f" — Indicação: {div.get('indicacao') or 'candidatura espontânea, sem indicação'!s}")

    partes.append("\n════ REGRAS ABSOLUTAS ════")
    partes.append(
        "- Responda EXCLUSIVAMENTE com base neste perfil; NUNCA invente experiência, formação ou "
        "certificação que não esteja listada acima.\n"
        "- Campos condicionais (\"caso Sim...\", subperguntas) → PULAR quando a condição não se aplica.\n"
        "- \"Já trabalhou nesta empresa?\" / \"é colaborador?\" → NÃO.\n"
        "- Confirmação de termos/privacidade → aceite (Sim).\n"
        "- Contradição entre a pergunta e a lista de exclusões → a lista de exclusões vence.")

    return "\n".join(partes)


def perfil_compacta(config: dict, env: Mapping[str, str] | None = None,
                    limite: int = 300) -> str:
    """Versão curta para prompts com teto de tokens — corta as seções iniciais
    mas NUNCA corta a lista de exclusões (regra de resposta, sempre por último)."""
    full = contexto_perfil(config, env)
    if len(full) <= limite:
        return full
    i = full.find('LISTA DE EXCLUSÕES')
    bloco_exc = full[i:] if i != -1 else ''
    if not bloco_exc:
        return full[:limite]
    resto = full[:max(0, limite - len(bloco_exc) - 10)]
    return (resto + "\n" + bloco_exc)[:limite]
