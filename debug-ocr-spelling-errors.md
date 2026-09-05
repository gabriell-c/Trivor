# Debug: Erros de digitação inventados pelo sistema

**Session ID:** ocr-spelling-errors
**Data:** 2026-08-31
**Problema:** O sistema reporta erros de digitação em palavras que na verdade são erros de OCR do PDF. Correções no `_correct_ocr_errors` estão incompletas.

## Palavras problemáticas identificadas:
- "operacionalis" → deveria ser "operacionais"
- "cadastroo" → deveria ser "cadastro"
- "Processoos" → deveria ser "Processos"
- "controlle" → deveria ser "controle"

## Hipóteses:
1. **H1:** O OCR fix map (`_correct_ocr_errors`) não inclui essas palavras específicas
2. **H2:** O replace acontece antes da normalização de espaços, e a palavra está ligeiramente diferente
3. **H3:** O LLM está processando o texto OCR como "erro de digitação" porque ele não é corrigido pelo fix
4. **H4:** A substituição está funcionando mas o LLM ainda detecta como erro porque a correção não cobre todos os casos

## Testes:
- [ ] Verificar o OCR fix map atual
- [ ] Adicionar logging para rastrear o que é detectado como erro
- [ ] Reproduzir o erro
- [ ] Adicionar correções
- [ ] Validar fix
