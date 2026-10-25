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
    _filtrar_ortografia_grounding,
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
