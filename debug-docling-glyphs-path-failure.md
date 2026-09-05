# Docling Unicode Bug - Debug & Resolution

## Problema
O C extension do `docling_parse` falha com Unicode em caminhos Windows (ex: `Á` em "Área de Trabalho").

**Erro original:**
```
RuntimeError: filename does not exists: .../pdf_resources/glyphs//standard/additional.dat
```

## Causa Raiz
- Issue #324 no GitHub do docling
- C extension usa `std::ifstream` com bytes UTF-8 no Windows, convertendo para ANSI codepage
- Path do arquivo PDF é corrigido no PR #326, mas paths de recursos internos continuam quebrados

## Solução Aplicada
Workaround em [main.py](file:///c:/Users/xxxsa/OneDrive/Área%20de%20Trabalho/python/curriculo/backend/main.py):

1. **Função `_ensure_docling_parse_ascii_path()`** (linhas 53-76):
   - Copia o pacote `docling_parse` para temp path ASCII
   - Injeta no `sys.path` antes dos site-packages
   - Limpa cache de módulos para forçar reimport

2. **Função `_extract_pdf_text_docling_parse()`** (linhas 79-125):
   - Usa API low-level do docling_parse diretamente
   - Evita dependência do pipeline completo do docling
   - Extrai texto por página usando `ContentLevel.COMPUTE_AND_MATERIALIZE`
   - Logging detalhado de erros por página

3. **Ordem de extração** (linhas 406-425):
   ```
   1. docling_parse (melhor qualidade estrutural)
   2. pdfplumber (fallback pure Python)
   3. pypdfium2 (fallback final)
   ```

4. **Garantia de path ASCII** (linhas 407-411):
   - PDF é copiado para path ASCII antes de passar para docling_parse
   - Evita problema de Unicode em caminhos temporários

## Status dos Testes
- ✅ Extração docling_parse: 17.879 chars (guia) e 558 chars (curriculo teste)
- ✅ API Analytics (localhost:20128): resposta 200
- ✅ Fluxo completo: PDF → extração → análise IA → resultado
- ⚠️ PDF da Milena: caindo em fallback (provavelmente escaneado/imagem)

## Limitações Conhecidas
- Pipeline completo do docling (com VLM) não funciona devido a dependência do torch
- Workaround requer cópia do pacote a cada restart do servidor
- Path ASCII é gerado em `tempfile.mkdtemp()`
- **PDFs escaneados/imagem** podem cair em fallback (necessita OCR)

## API Key de Teste
- **Chave**: `sk-64d74435382a0e43-76a991-f16aeff1`
- **URL base**: `http://localhost:20128/v1`
- **Modelo**: `auto/best-coding` (DeepSeek-V3.2)

## Diagnóstico de Fallback
Se o PDF estiver caindo em fallback:
1. Verifique se o PDF tem texto selecionável (clique e arraste no PDF)
2. Verifique os logs do servidor para ver o erro exato
3. Se for PDF escaneado, considere usar OCR (tesseract)

Ver [diagnostico_fallback.md](file:///c:/Users/xxxsa/OneDrive/Área%20de%20Trabalho/python/curriculo/docs/diagnostico_fallback.md) para mais detalhes.
