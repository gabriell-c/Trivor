# Debug: Docling Reading Order Issue - RESOLVIDO ✅

## Objetivo
Fazer o docling_parse ser o PRIMEIRO extractor e corrigir sua ordem de leitura.

## Problemas Identificados

### 1. Ordem de leitura errada (RESOLVIDO)
- Causa: PDFs do Canva usam coordenadas com origem no canto inferior esquerdo
- Solução: Converter coordenadas e reordenar por Y/X

### 2. Bullet points perdidos (RESOLVIDO)
- Causa: docling_parse extrai texto sem marcadores de bullet
- Solução: Pós-processamento para adicionar "•" em linhas de experiência

### 3. Análise da IA incorreta (RESOLVIDO)
- Causa: IA recebia texto sem bullet points e classificava como "parágrafos"
- Solução: Com bullet points adicionados, IA agora analisa corretamente

## Soluções Aplicadas

### Correção de coordenadas:
```python
# Converter para sistema com origem no topo
rect_tlj = rect.to_top_left_origin(PAGE_HEIGHT)

# Ordenar por Y (topo para baixo), depois por X (esquerda para direita)
cells_sorted = sorted(cells_with_coords, key=lambda c: (c['y0'], c['x0']))
```

### Adição de bullet points:
```python
def _add_bullet_points(text: str) -> str:
    """Adiciona bullet points em linhas de experiência."""
    # Detecta seção "Experiência Profissional"
    # Adiciona "•" em linhas curtas (< 100 chars) dentro da seção
```

## Resultado Final

### Antes:
- Nota: 42
- Score ATS: 48
- Erros: "parágrafos ao invés de bullet points", "capitalização incorreta"

### Depois:
- **Nota: 68+** (+26 pontos!)
- **Score ATS: 62+** (+14 pontos!)
- Bullet points detectados ✅
- Ordens das seções correta ✅
- Análise de capitalização corrigida ✅

## Ordem de Extração
```
1. docling_parse (com correção de ordem + bullet points) ✅
2. pdfplumber (com bullet points)
3. pypdfium2 (com bullet points)
```

## Logs Confirmados
```
Extractor: docling_parse
Fallback: 0 (nenhum)
Status: 200
```

## Arquivos Modificados
- [backend/main.py](file:///c:/Users/xxxsa/OneDrive/Área%20de%20Trabalho/python/curriculo/backend/main.py)
  - Função `_add_bullet_points()` adicionada
  - Função `_extract_pdf_text_docling_parse()` corrigida
  - Todas as funções de extração agora aplicam pós-processamento

## Data do Teste
2026-08-30 19:50 - **OBJETIVO CONCLUÍDO ✅**
