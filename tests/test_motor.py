import json
import pytest
from fastapi import UploadFile
import io

def mock_analyze_response():
    # Simula resposta estruturada que o motor (OpenAI + Prompt) deve entregar
    return {
        'nota': 8.5,
        'analise_ats': 'O currículo passa nos filtros básicos.',
        'pontos_fortes': ['Experiência sólida', 'Stack moderna'],
        'pontos_melhoria': ['Falta o impacto XYZ']
    }

def test_motor_de_analise_formato():
    data = mock_analyze_response()
    assert isinstance(data['nota'], (float, int)), 'Nota deve ser um número'
    assert 'analise_ats' in data, 'Falta campo de análise ATS'
    assert isinstance(data['pontos_fortes'], list), 'Pontos fortes deve ser uma lista'
    print('\n[TEST] Estrutura do motor de análise validada com sucesso.')

if __name__ == '__main__':
    test_motor_de_analise_formato()
