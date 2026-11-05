"""
Testes de caracterização dos filters puros de anti-alucinação do analyze_cv,
extraídos de cv_routes.analyze_cv para cv_helpers (refatoração de complexidade).

São characterization tests: codificam o comportamento ATUAL dos filtros com
inputs sintéticos, sem depender de LLM nem de servidor. Se a saída mudar,
o teste falha e obriga revisão consciente.

Executar: pytest tests/test_cv_filters.py -v
"""
import sys
from pathlib import Path

# Adiciona backend ao path para importar cv_helpers diretamente
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from cv_helpers import (
    _blindar_falsos_positivos,
    _check_chronological_order,
    _filtrar_ortografia_grounding,
    _term_in_text,
    _validar_citacoes,
)


# ---------------------------------------------------------------------------
# _validar_citacoes — citações literais têm que existir no texto do CV
# ---------------------------------------------------------------------------
class TestValidarCitacoes:
    def test_citacao_real_mantida_e_inventada_removida(self):
        markdown = (
            "Maria Silva\n"
            "Analista de suporte com 4 anos de experiência\n"
            "Comunicação e atendimento ao cliente\n"
        )
        analysis = {
            "pontos_fortes": [
                "Experiência relevante (trecho: 'Analista de suporte com 4 anos de experiência')",
            ],
            "pontos_fracos": [
                "Trecho inventado (trecho: 'nada que exista no CV')",
            ],
        }

        _validar_citacoes(analysis, markdown)

        # Citação que existe no texto é preservada
        assert analysis["pontos_fortes"] == [
            "Experiência relevante (trecho: 'Analista de suporte com 4 anos de experiência')"
        ]
        # Citação inválida é cortada, mas o item sobrevive sem o trecho
        assert analysis["pontos_fracos"] == ["Trecho inventado"]

    def test_campo_que_nao_e_lista_ignorado(self):
        analysis = {"pontos_fortes": "texto solto", "pontos_fracos": None}
        # Não deve estourar e não deve reescrever campos que não são list
        _validar_citacoes(analysis, "qualquer texto")
        assert analysis["pontos_fortes"] == "texto solto"
        assert analysis["pontos_fracos"] is None


# ---------------------------------------------------------------------------
# _filtrar_ortografia_grounding — erros têm que estar grounded no texto
# ---------------------------------------------------------------------------
class TestFiltrarOrtografiaGrounding:
    def test_somente_palavra_que_existe_no_texto_sobrevive(self):
        markdown = "Experiência na empresa ACME por 2 anos\n"
        analysis = {
            "erros_ortograficos": [
                {"palavra": "empresa", "correcao": "empresaa"},          # existe + correção difere → MANTÉM
                {"palavra": "palavrainexistente", "correcao": "x"},     # não está no texto → corta
                {"palavra": "EMPRESA", "correcao": "empresa"},          # tudo em caixa alta = capitalização → corta
            ],
        }

        _filtrar_ortografia_grounding(analysis, markdown)

        assert analysis["erros_ortograficos"] == [
            {"palavra": "empresa", "correcao": "empresaa"}
        ]

    def test_correcao_igual_a_palavra_e_cortada(self):
        markdown = "uso da palavra corretamente aqui\n"
        analysis = {
            "erros_ortograficos": [
                {"palavra": "corretamente", "correcao": "corretamente"},  # igual → falso positivo
            ],
        }

        _filtrar_ortografia_grounding(analysis, markdown)

        assert analysis["erros_ortograficos"] == []


# ---------------------------------------------------------------------------
# _blindar_falsos_positivos — viés dev sem área + consistência narrativa
# ---------------------------------------------------------------------------
class TestBlindarFalsosPositivos:
    def test_sem_area_zera_vies_dev_e_malha_narrativa(self):
        markdown = "Maria Silva. Analista de suporte com 4 anos. Comunicação com clientes."
        analysis = {
            "pontos_fracos": [
                "Falta experiência com framework React",      # viés dev (sem área) → corta
                "Comunicação fraca no atendimento",           # genérico, sem menção a ortografia/OCR → MANTÉM
                "Apresenta erros ortográficos no texto",      # alega ortografia mas não há erros → corta
            ],
            "erros_ortograficos": [],
        }

        _blindar_falsos_positivos(analysis, markdown, area_info="")

        # Sem área informada: palavras-chave faltantes são zeradas
        assert analysis["palavras_chave_faltantes"] == []
        # Só sobrevive o ponto genérico que não tem viés dev nem alega ortografia
        assert analysis["pontos_fracos"] == ["Comunicação fraca no atendimento"]

    def test_com_area_nao_aplica_filtro_de_vies_dev(self):
        # Com área informada, a seção 2 (viés dev) é pulada: o ponto tech
        # sobrevive e palavras_chave_faltantes nem é criado.
        markdown = "Maria Silva. Analista de suporte com 4 anos."
        analysis = {
            "pontos_fracos": [
                "Falta experiência com framework React",
            ],
            "erros_ortograficos": [],
        }

        _blindar_falsos_positivos(analysis, markdown, area_info="tecnologia")

        # Seção 4 (consistência narrativa): sem erros ortográficos, mas o ponto
        # não menciona ortografia/OCR → sobrevive
        assert analysis["pontos_fracos"] == ["Falta experiência com framework React"]
        assert "palavras_chave_faltantes" not in analysis


# ---------------------------------------------------------------------------
# _check_chronological_order — L1: faixas de ano não podem ser
# interpretadas como duas experiências separadas
# ---------------------------------------------------------------------------
class TestCheckChronologicalOrder:
    def test_faixa_em_ordem_nao_flaga(self):
        # "2024-2026" seguida de "2021-2023" → anos de início [2024, 2021]
        # decrescente → ordem correta. Antes cada padrão de regex
        # alimentava a lista em série e a faixa sozinha virava [2024, 2026],
        # quebrando a monotonia.
        text = (
            "Experiência:\n"
            "ACME Corp — 2024-2026\n"
            "Beta Ltda — 2021-2023\n"
        )
        r = _check_chronological_order(text)
        assert r["cronologica"] is True
        assert r["problema"] is None

    def test_faixa_fora_de_ordem_flaga(self):
        text = (
            "Experiência:\n"
            "ACME Corp — 2021-2023\n"
            "Beta Ltda — 2024-2026\n"
        )
        r = _check_chronological_order(text)
        assert r["cronologica"] is False
        assert "cronol" in (r["problema"] or "").lower()

    def test_mes_com_de_e_faixa(self):
        # "mar. de 2024 - dez. de 2026" é UM período (início 2024),
        # não duas datas. A segunda experiência começa em 2021.
        text = (
            "ACME, mar. de 2024 - dez. de 2026\n"
            "Beta, jan. de 2021 - mar. de 2024\n"
        )
        assert _check_chronological_order(text)["cronologica"] is True

    def test_faixa_ate_presente(self):
        text = (
            "ACME — 2024-presente\n"
            "Beta — 2020-2023\n"
        )
        assert _check_chronological_order(text)["cronologica"] is True

    def test_datas_simples_ordenadas(self):
        text = (
            "ACME, mar. de 2024\n"
            "Beta, mar. de 2021\n"
        )
        assert _check_chronological_order(text)["cronologica"] is True

    def test_datas_simples_fora_de_ordem(self):
        text = (
            "ACME, mar. de 2021\n"
            "Beta, mar. de 2024\n"
        )
        assert _check_chronological_order(text)["cronologica"] is False

    def test_dupe_dois_padraos_mesma_faixa(self):
        # "2024-2026" casa em dois padrões ao mesmo tempo; tem que
        # dedupar e contar o período UMA vez.
        text = (
            "ACME — 2024-2026\n"
            "Beta — 2019-2020\n"
        )
        assert _check_chronological_order(text)["cronologica"] is True

    def test_poucas_datas_nao_avalia(self):
        text = "ACME — 2024-2026"
        r = _check_chronological_order(text)
        assert r["cronologica"] is True


# ---------------------------------------------------------------------------
# _term_in_text — L10: números e tempo não podem satisfazer o requisito
# ---------------------------------------------------------------------------
class TestTermInText:
    def test_tempo_e_stopwords_nao_satisfazem(self):
        # "3 anos de experiência com Python": Python não está no CV →
        # 'anos' (stopword/tempo) não deve cobrir o requisito.
        cv_norm = "3 anos de experiencia"
        assert _term_in_text("3 anos de experiência com Python", cv_norm) is False

    def test_skill_restante_satisfeita(self):
        cv_norm = "3 anos de experiencia com python"
        assert _term_in_text("3 anos de experiência com Python", cv_norm) is True

    def test_so_stopwords_inavaliavel(self):
        # Requisito 100% de stopword ("experiência com sistemas") não pode
        # virar "coberto" só porque o CV tem essas palavras genéricas.
        # (Ordem embaralhada para o match de frase inteira não bater —
        # cada palavra aparece isolada, como em CV real.)
        cv_norm = "trabalho com sistemas e experiencia"
        assert _term_in_text("experiência com sistemas", cv_norm) is False
