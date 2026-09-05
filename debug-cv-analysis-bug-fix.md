# Debug Session: CV Analysis Issues

**Session ID:** cv-analysis-bug-fix
**Data:** 2026-08-30
**Status:** Correções aplicadas — aguardando teste

## Problemas Relatados

1. **Erros ortográficos inventados** — O modelo reportava erros que não existem
2. **Prompt específico para vagas de DEV** — A análise não era genérica
3. **Bullet points não detectados** — O texto tinha bullets mas o modelo não reconhecia

## Hipóteses Validadas

| # | Hipótese | Status |
|---|----------|--------|
| 1 | `pyspellchecker` é um corretor **inglês** aplicado a texto em português → falsos positivos em nomes como "Cardoso", "Sebastião" | ✅ Confirmada |
| 2 | `target_role` tinha default `"fullstack"` → força análise para vagas de DEV quando o usuário não informa nada | ✅ Confirmada |
| 3 | Regex de bullet só captava início absoluto de linha; docling_parse pode adicionar espaços antes do marcador | ✅ Confirmada |

## Correções Aplicadas

### 1. SpellChecker desativado
- `_spell_check()` agora é **no-op** (retorna o texto inalterado)
- Explicação: `pyspellchecker` não tem dicionário português; mesmo com `load_words()`, palavras como sobrenomes geram falsos positivos que o LLM interpreta como "erros reais" a corrigir

### 2. Prompt genérico para qualquer área
- `target_role` default mudou de `"fullstack"` → `""`
- Instrução adicionada: *"Se nenhuma área/vaga for especificada, faça uma análise geral e universal (válida para qualquer profissão)"*
- `"tech_so_skills"` renomeado para `"skills_soletivas"` no JSON schema
- `"false para tecnologia e a maioria das demais"` → `"false para a maioria das demais áreas"`

### 3. Bullet detection melhorado
- Regex expandido: `[\u2022\u2023\-\*]` → `[•·\-*\u2022\u2023\u2713\u25cf\u25b8]`
- Inclui: `•` (bullet), `·` (middle dot), `*` (asterisk), `✓` (check), `●` (bullet), `▸` (right arrow)
- Limpeza de espaços múltiplos adicionada: `re.sub(r'\s{2,}', ' ', stripped)`
- Linha de chave-valor agora **nunca** vira cabeçalho (ex: `Endereço: Sebastião ...`)

### 4. Correções de OCR adicionadas
- `_correct_ocr_errors()`: `ants→anos`, `mess→meses`, `retinas→rotinas`
- Aplicado antes da conversão para Markdown

### 5. Instrumentação
- Log adicionado: `[CV] Markdown gerado (N chars): ...` — mostra os primeiros 800 chars do markdown antes de enviar ao LLM
- Útil para depurar bugs futuros de formatação

## Servidor
- Rodando em **http://0.0.0.0:8002** (porta 8000 ocupada por processo alheio)
- Reinicie com: `python main.py` (no terminal com venv ativado)
