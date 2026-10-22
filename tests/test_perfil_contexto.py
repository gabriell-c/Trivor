"""
Testes do contexto de perfil único (apply/common/perfil.py).

O módulo é o que os 5 bots injetam nos prompts dos LLMs — ele precisa
montar TODAS as seções do perfil (config.yaml + .env) e traduzir a lista
negativa em regras de resposta ("sabe Java?" → NÃO).
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _carregar_perfil():
    p = ROOT / 'apply' / 'common' / 'perfil.py'
    spec = importlib.util.spec_from_file_location('apply_perfil_teste', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


perfil = _carregar_perfil()


def _config_completo() -> dict:
    """Fixtures 100% fictícios — nunca PII real (repositório público)."""
    return {
        'candidato': {
            'nome': 'Ana da Silva',
            'data_nascimento': '2003-11-10',
            'email': 'ana@exemplo.com',
            'telefone': '11999990000',
            'cidade_uf': 'São Paulo - SP',
            'linkedin': 'https://linkedin.com/in/x',
            'github': 'https://github.com/x',
            'portfolio': 'x.vercel.app',
            'nivel_ingles': 'Basic',
            'disponibilidade_dias': 1,
            'possui_pj': False,
            'pretensao_clt': '3000',
            'pretensao_pj_hora': '22',
            'pretensao_pj_mensal': '4500',
            'pretensao_estagio': '1600',
            'formacao': {'curso': 'Engenharia de Software', 'instituicao': 'Instituição X',
                         'ano_conclusao': '2029', 'situacao': 'Cursando'},
            'certificacoes': ['AWS Cloud Practitioner: 2025', 'B7Web: HTML: 2024'],
            'experiencia': ['Freelancer Python/React: 2022-2026'],
            'idiomas': ['Espanhol: Básico'],
            'sobre': 'Desenvolvedor júnior focado em backend Python e automações.',
            'inicio': 'Imediata',
            'horas_semana': '40',
        },
        'endereco': {'pais': 'Brasil', 'estado_nome': 'São Paulo', 'estado_uf': 'SP',
                     'cidade': 'São Paulo', 'logradouro': 'Rua Teste',
                     'numero': '123', 'complemento': '', 'bairro': 'Centro',
                     'cep': '14010-000'},
        'diversidade': {'raca_cor': 'Pardo', 'genero': 'Homem cisgênero',
                        'orientacao_sexual': 'Heterossexual', 'pcd': False,
                        'indicacao': 'espontânea'},
        'localizacao': {'aceita_remoto': True, 'aceita_hibrido': True, 'aceita_presencial': True,
                        'aceita_mudanca': True, 'estados_aceitos': ['SP', 'MG']},
        'busca': {'nivel': ['estágio', 'júnior'],
                  'palavras_excluir': ['sênior', 'java', 'kotlin', 'mobile']},
        'tecnologias': {'Python': 'De 2 anos até 3 anos', 'JavaScript': 'De 2 anos até 3 anos'},
    }


def test_contexto_inclui_todas_as_secoes():
    texto = perfil.contexto_perfil(_config_completo(), env={
        'CANDIDATO_CPF': '111.444.777-88', 'CANDIDATO_NOME_PAI': 'Pai Teste',
        'CANDIDATO_NOME_MAE': 'Mãe Teste', 'CANDIDATO_NACIONALIDADE': 'Brasileira',
    })
    for esperado in [
        'Ana da Silva', '111.444.777-88', 'Pai Teste', 'Mãe Teste', 'Brasileira',
        'Engenharia de Software', 'Instituição X', 'Cursando', 'AWS Cloud Practitioner: 2025',
        'Freelancer Python/React: 2022-2026', 'Espanhol: Básico',
        'Python: De 2 anos até 3 anos', 'java', 'Pardo', 'SP', '3000',
        'Rua Teste', 'LISTA DE EXCLUSÕES',
    ]:
        assert esperado in texto, f'falta no contexto: {esperado!r}'


def test_endereco_do_env_tem_prioridade():
    cfg = _config_completo()
    texto = perfil.contexto_perfil(cfg, env={'ENDERECO_CEP': '99999-999', 'ENDERECO_BAIRRO': 'Recanto'})
    secao = texto.split('ENDEREÇO', 1)[1].split('FORMAÇÃO', 1)[0]
    assert '99999-999' in secao      # override do .env
    assert 'Recanto' in secao
    assert 'Centro' not in secao      # valor do config caiu (o .env manda)


def test_sem_env_chama_os_environ(monkeypatch):
    # env=None → lê os.environ (o bot fez load_dotenv no import)
    cfg = _config_completo()
    texto = perfil.contexto_perfil(cfg)
    assert 'CPF:' in texto  # seção existe mesmo sem valor


def test_sem_nada_na_config_nao_quebra():
    texto = perfil.contexto_perfil({}, env=None)
    assert '(não informado)' in texto
    assert 'LISTA DE EXCLUSÕES' in texto
    assert '(lista vazia' in texto


def test_regra_de_exclusao_para_pergunta_de_tech():
    texto = perfil.contexto_perfil(_config_completo(), env=None)
    trecho = texto.split('LISTA DE EXCLUSÕES')[1]
    assert 'responda NÃO' in trecho
    assert 'Nenhum' in trecho  # regra de nível por tecnologia


def test_idade_formato_dd_maaa_do_config_real():
    # O config.yaml guarda DD/MM/AAAA (a UI grava isoParaDmy); o contexto
    # tem que calcular a idade com esse formato, não só com ISO.
    cfg = _config_completo()
    cfg['candidato']['data_nascimento'] = '10/11/2003'
    assert 'anos (nascido em 10/11/2003)' in perfil.contexto_perfil(cfg, env=None)
    cfg['candidato']['data_nascimento'] = 'nada-aqui'
    assert 'Idade:' not in perfil.contexto_perfil(cfg, env=None)


def test_campos_novos_educacao_e_disponibilidade():
    texto = perfil.contexto_perfil(_config_completo(), env=None)
    for esperado in [
        'Desenvolvedor júnior focado em backend Python e automações',  # sobre
        'Início: Imediata',                                              # inicio
        'Carga horária: 40',                                             # horas_semana
        'conclusão 2029',                                                # formacao.ano_conclusao
    ]:
        assert esperado in texto, f'falta no contexto: {esperado!r}'


def test_tech_excluida_fronteira_de_palavra():
    neg = ['java', 'aws']
    assert perfil.tech_excluida('Java', neg) is True
    assert perfil.tech_excluida('Java SE', neg) is True
    assert perfil.tech_excluida('JAVASCRIPT', neg) is False   # não é o mesmo token
    assert perfil.tech_excluida('aws (amazon web services)', neg) is True
    assert perfil.tech_excluida('Spring', neg) is False
    assert perfil.tech_excluida('', neg) is False
    assert perfil.tech_excluida('Java', []) is False


def test_tech_excluida_senioridade():
    neg = ['sênior', '5 anos']
    assert perfil.tech_excluida('Sênior', neg) is True
    assert perfil.tech_excluida('Júnior', neg) is False


def test_contexto_ignora_senhas_do_env():
    cfg = _config_completo()
    texto = perfil.contexto_perfil(cfg, env={'GUPY_SENHA': 'segredo-1234'})
    assert 'segredo-1234' not in texto


def test_perfil_compacta_preserva_exclusoes():
    cfg = _config_completo()
    curta = perfil.perfil_compacta(cfg, limite=500)
    assert len(curta) <= 500
    assert 'EXCLUSÕES' in curta
    assert 'java' in curta
