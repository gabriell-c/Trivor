"""
Property/fuzz tests (hypothesis) para os parsers e transforms puros de
backend/market_service.py — invariantes das funções, não o output de hoje:

- _parse_br_number: formato BR (milhar '.', decimal ',') → float
- normalize_term / normalize_skill: idempotência e estabilidade
- sanitize: remoção de surrogates
- _is_garbage_requirement: entrada só dígitos/pontuação é sempre lixo
- _keyword_score: score permissivo, nunca zera
"""
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

BACKEND_PATH = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_PATH))

import market_service as ms

# Fuzz de parsers não precisa de exemplos duráveis (não há replay a manter)
_FAST = settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)

_SURROGATES = [chr(c) for c in range(0xD800, 0xDC00, 16)] + ["a", "b", "ç", "é"]


class TestParseBrNumber:
    """'8.000' é milhar, '8.000,50' é 8000.5 — o parser nunca troca os papéis."""

    @_FAST
    @given(st.integers(min_value=0))
    def test_inteiro_groupado_br(self, n: int):
        s = f"{n:,}".replace(",", ".")
        assert ms._parse_br_number(s) == float(n)

    @_FAST
    @given(st.integers(min_value=0), st.integers(min_value=0, max_value=99))
    def test_centavos_br(self, reais: int, centavos: int):
        s = f"{reais:,}".replace(",", ".") + f",{centavos:02d}"
        esperado = reais + centavos / 100
        assert abs(ms._parse_br_number(s) - esperado) < 1e-6

    @given(st.sampled_from(["", "  ", "\t"]))
    def test_vazio_levanta(self, s: str):
        with pytest.raises(ValueError):
            ms._parse_br_number(s)


class TestNormalizeTerm:
    @_FAST
    @given(st.text())
    def test_idempotente(self, x: str):
        assert ms.normalize_term(ms.normalize_term(x)) == ms.normalize_term(x)

    @_FAST
    @given(st.text())
    def test_colapsa_espacos(self, x: str):
        out = ms.normalize_term(x)
        assert out == " ".join(out.split())


class TestNormalizeSkill:
    """Saída canônica: sem lixo, sem espaços extras, estável sob minúsculas."""

    @_FAST
    @given(st.from_regex(r"^[\d\s.,%\-/]+$"))
    def test_garbage_vira_vazio(self, x: str):
        assert ms.normalize_skill(x) == ""

    @_FAST
    @given(st.text())
    def test_sem_espaco_extra(self, x: str):
        out = ms.normalize_skill(x)
        assert out == "" or out == " ".join(out.split())

    @_FAST
    @given(st.text())
    def test_estavel_ao_minimizar(self, x: str):
        # A normalização já faz .lower() internamente — minúsculas não mudam o resultado
        assert ms.normalize_skill(x.lower()) == ms.normalize_skill(x)


class TestSanitize:
    @_FAST
    @given(st.text())
    def test_idempotente(self, x: str):
        assert ms.sanitize(ms.sanitize(x)) == ms.sanitize(x)

    @_FAST
    @given(st.text(alphabet=st.sampled_from(_SURROGATES)))
    def test_remove_surrogates(self, x: str):
        out = ms.sanitize(x)
        assert all(not (0xD800 <= ord(c) <= 0xDFFF) for c in out)


class TestGarbageRequirement:
    @_FAST
    @given(st.from_regex(r"^[\d\s.,%\-/]+$"))
    def test_somente_digitos_e_pontuacao(self, x: str):
        assert ms._is_garbage_requirement(x) is True


class TestKeywordScore:
    """Invariante documentada: score permissivo — nunca zera a vaga."""

    @_FAST
    @given(st.text(), st.text())
    def test_nunca_zero(self, job_text: str, job_title: str):
        score = ms._keyword_score(
            job_text.lower(), job_title, ["Python"], "Pleno", "Remoto Nacional"
        )
        assert score >= 1
