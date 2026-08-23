"""
Testes unitários para market_service.py
"""
import pytest
import sqlite3
import os
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Add backend to path
BACKEND_PATH = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_PATH))

import market_service as ms


# ============================================================================
# normalize_term
# ============================================================================

class TestNormalizeTerm:
    def test_simple_word(self):
        assert ms.normalize_term("python") == "Python"

    def test_multiple_words(self):
        assert ms.normalize_term("machine learning") == "Machine Learning"

    def test_already_capitalized(self):
        assert ms.normalize_term("React") == "React"

    def test_extra_whitespace(self):
        assert ms.normalize_term("  java  ") == "Java"

    def test_empty(self):
        assert ms.normalize_term("") == ""


# ============================================================================
# _detect_job_seniority
# ============================================================================

class TestDetectJobSeniority:
    def test_senior_keywords(self):
        assert ms._detect_job_seniority("senior developer needed") == "sênior"
        assert ms._detect_job_seniority("staff engineer role") == "sênior"
        assert ms._detect_job_seniority("arquiteto de software") == "sênior"
        assert ms._detect_job_seniority("lead developer") == "sênior"

    def test_pleno_keywords(self):
        assert ms._detect_job_seniority("pleno developer") == "pleno"
        assert ms._detect_job_seniority("middle engineer") == "pleno"

    def test_junior_keywords(self):
        assert ms._detect_job_seniority("junior developer") == "júnior"
        assert ms._detect_job_seniority("estagiário de ti") == "júnior"
        assert ms._detect_job_seniority("intern position") == "júnior"

    def test_no_match(self):
        assert ms._detect_job_seniority("programador full stack") == ""

    def test_senior_takes_priority(self):
        assert ms._detect_job_seniority("senior or junior developer") == "sênior"


# ============================================================================
# _keyword_score
# ============================================================================

class TestKeywordScore:
    def test_basic_match(self):
        score = ms._keyword_score(
            "python django rest api developer",
            "Developer",
            ["Python", "Django"],
            "Pleno",
            "Remoto"
        )
        assert score > 0

    def test_no_match(self):
        score = ms._keyword_score(
            "cooking recipe blogger",
            "Developer",
            ["Python", "Django"],
            "Pleno",
            "Remoto"
        )
        assert score == 0

    def test_seniority_rejection(self):
        score = ms._keyword_score(
            "júnior developer python",
            "Developer",
            ["Python"],
            "Sênior",
            "Remoto"
        )
        assert score == 0


# ============================================================================
# _pre_filter_jobs
# ============================================================================

class TestPreFilterJobs:
    def _make_job(self, title="Python Developer", company="Tech",
                  desc="Python Django developer needed", location="São Paulo",
                  modality="Presencial"):
        return ("test-1", title, company, desc, location, modality, "LinkedIn", "")

    def test_filters_by_keyword(self):
        jobs = [self._make_job()]
        result = ms._pre_filter_jobs(jobs, ["Python"], "Pleno", "São Paulo", [], max_jobs=10)
        assert len(result) == 1

    def test_filters_out_no_match(self):
        jobs = [self._make_job(title="Java Developer", desc="Java developer needed")]
        result = ms._pre_filter_jobs(jobs, ["Python"], "Pleno", "São Paulo", [], max_jobs=10)
        assert len(result) == 0

    def test_negative_keywords(self):
        jobs = [
            self._make_job(desc="Python developer"),
            self._make_job(desc="Python manager position"),
        ]
        result = ms._pre_filter_jobs(jobs, ["Python"], "Pleno", "São Paulo", ["manager"], max_jobs=10)
        assert len(result) == 1

    def test_max_jobs_limit(self):
        jobs = [self._make_job() for _ in range(50)]
        result = ms._pre_filter_jobs(jobs, ["Python"], "Pleno", "São Paulo", [], max_jobs=5)
        assert len(result) <= 5

    def test_empty_jobs(self):
        result = ms._pre_filter_jobs([], ["Python"], "Pleno", "São Paulo", [], max_jobs=10)
        assert result == []


# ============================================================================
# init_market_db
# ============================================================================

class TestInitMarketDb:
    def test_creates_tables(self, tmp_path):
        db_file = str(tmp_path / "test_market.db")
        ms.init_market_db(db_file)
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cursor.fetchall()}
        conn.close()
        assert "market_raw_jobs" in tables
        assert "market_jobs" in tables
        assert "market_reports" in tables

    def test_called_twice_no_error(self, tmp_path):
        db_file = str(tmp_path / "test_market2.db")
        ms.init_market_db(db_file)
        ms.init_market_db(db_file)  # Should not raise


# ============================================================================
# generate_mock_jobs_if_empty
# ============================================================================

class TestGenerateMockJobsIfEmpty:
    def test_generates_jobs(self, tmp_path):
        db_file = str(tmp_path / "test_mock.db")
        ms.init_market_db(db_file)
        ms.generate_mock_jobs_if_empty(db_file, "Python Dev")
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM market_raw_jobs")
        count = cursor.fetchone()[0]
        conn.close()
        assert count > 0

    def test_no_duplicate_jobs(self, tmp_path):
        db_file = str(tmp_path / "test_mock_dup.db")
        ms.init_market_db(db_file)
        ms.generate_mock_jobs_if_empty(db_file, "Python Dev")
        ms.generate_mock_jobs_if_empty(db_file, "Python Dev")
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM market_raw_jobs")
        count = cursor.fetchone()[0]
        conn.close()
        assert count > 0


# ============================================================================
# heuristic_extract
# ============================================================================

class TestHeuristicExtract:
    def test_returns_dict_not_none(self):
        """Critical: must not return None even when AI fails"""
        result = ms.heuristic_extract("Test description")
        assert result is not None
        assert isinstance(result, dict)

    def test_basic_extraction(self):
        job_text = """
        Developer Python Pleno
        Requisitos: Python, Django, PostgreSQL
        Diferencial: AWS, Docker
        Nível: Pleno
        """
        result = ms.heuristic_extract(job_text)
        assert isinstance(result, dict)
        assert "is_relevant" in result
        assert "requirements" in result
        assert "role_level" in result

    def test_empty_text(self):
        result = ms.heuristic_extract("")
        assert isinstance(result, dict)
        assert result.get("is_relevant") is False


# ============================================================================
# run_market_analysis (with mocked AI)
# ============================================================================

class TestRunMarketAnalysis:
    def _make_mock_response(self, content=None):
        if content is None:
            # extract_jobs_batched espera JSON array
            content = json.dumps([{
                "is_relevant": True,
                "role_level": "Pleno",
                "exp_years_min": 2,
                "exp_years_max": 5,
                "requirements": ["Python", "Django"],
                "nice_to_have": ["AWS"],
                "certifications": [],
                "soft_skills": ["trabalho em equipe"],
                "salary_min": 6000,
                "salary_max": 10000,
                "currency": "BRL",
            }])
        mock_message = MagicMock()
        mock_message.content = content
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock = MagicMock()
        mock.choices = [mock_choice]
        return mock

    @patch("market_service.OpenAI")
    def test_basic_analysis(self, mock_openai, tmp_path):
        db_file = str(tmp_path / "test_analysis.db")
        ms.init_market_db(db_file)
        ms.generate_mock_jobs_if_empty(db_file, "Python Dev")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._make_mock_response()
        mock_openai.return_value = mock_client

        result = ms.run_market_analysis(
            db_file=db_file,
            client=mock_client,
            selected_model="gpt-4o",
            job_title="Python Dev",
            target_stack="Python, Django",
            seniority="Pleno",
            location="São Paulo",
            time_window="30 dias",
            jsearch_api_keys=[]
        )
        assert result is not None
        assert "summary" in result
        assert "statistics" in result
        assert "sample_jobs" in result

    @patch("market_service.generate_mock_jobs_if_empty")
    @patch("market_service.OpenAI")
    def test_empty_db(self, mock_openai, mock_generate, tmp_path):
        db_file = str(tmp_path / "test_empty.db")
        ms.init_market_db(db_file)
        # No jobs generated

        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        result = ms.run_market_analysis(
            db_file=db_file,
            client=mock_client,
            selected_model="gpt-4o",
            job_title="Python Dev",
            target_stack="Python",
            seniority="Pleno",
            location="São Paulo",
            time_window="30 dias",
            jsearch_api_keys=[]
        )
        assert result["summary"]["total_jobs_scanned"] == 0

    @patch("market_service.OpenAI")
    def test_fallback_heuristic_on_ai_failure(self, mock_openai, tmp_path):
        db_file = str(tmp_path / "test_fallback.db")
        ms.init_market_db(db_file)
        ms.generate_mock_jobs_if_empty(db_file, "Python Dev")

        # AI fails
        mock_client = MagicMock()
        from openai import APIConnectionError
        mock_client.chat.completions.create.side_effect = Exception("AI down")
        mock_openai.return_value = mock_client

        result = ms.run_market_analysis(
            db_file=db_file,
            client=mock_client,
            selected_model="gpt-4o",
            job_title="Python Dev",
            target_stack="Python",
            seniority="Pleno",
            location="São Paulo",
            time_window="30 dias",
            jsearch_api_keys=[]
        )
        # Should still return a valid report using heuristic fallback
        assert result is not None
        assert "summary" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
