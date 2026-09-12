# Plano de Aprimoramento da Extração de Currículos

## Resumo
Objetivo: tornar o pipeline de extração de currículos capaz de:
1. Detectar a ordem real das seções (dados pessoais, experiência, formação, habilidades).
2. Identificar bullets reais e distinguir de linhas normais.
3. Reconhecer hyperlinks válidos (não apenas strings "https").
4. Corrigir erros ortográficos óbvios, ignorando termos técnicos/inglês.
5. Normalizar cabeçalhos e capitalização.
6. Gerar um Markdown estruturado que sirva de entrada para o LLM, com prompt aprimorado.

## Estado Atual
- `backend/main.py` já contém a extração usando `docling_parse` (ou fallback) e ordenação por coordenadas.
- Não há conversão para Markdown nem validações de bullets, links ou ortografia.
- O prompt enviado ao LLM está genérico e não instrui sobre estrutura Markdown.
- Não há cache nem validação pós‑extração.

## Mudanças Propostas
| Arquivo | Alteração | Por quê | Como |
|---------|-----------|---------|------|
| `backend/main.py` | **Função `_text_to_markdown(text)`** – converte texto bruto em Markdown (cabeçalhos, listas, parágrafos). | Fornece estrutura clara ao LLM, facilita detecção de bullets e ordem de seções. | Implementar regex para cabeçalhos (`^[A-Z][A-Z ]+$` ou linhas terminadas em `:`) → `##`. Detectar marcadores reais (`^[\s]*[\u2022\u2023\-\*]\s+`) → `-`. Preservar linhas vazias como quebras de parágrafo. |
| `backend/main.py` | **Função `_detect_hyperlinks(text)`** – retorna lista de URLs válidas (uso `urllib.parse` e `requests.head` com timeout 2 s). | Permite indicar ao LLM quais links são reais e funcionais. | Percorrer linhas, extrair padrões `https?://\S+`, validar esquema e domínio, opcionalmente fazer HEAD request. |
| `backend/main.py` | **Função `_spell_check(text)`** – corrige erros ortográficos usando `pyspellchecker` com dicionário customizado (palavras técnicas, nomes próprios, termos em inglês). | Melhora a qualidade da extração e evita “palavras erradas”. | Aplicar apenas em linhas que não são cabeçalhos nem URLs. Ignorar palavras que contenham letras maiúsculas internas ou números. |
| `backend/main.py` | **Integração** – após `_extract_pdf_text_docling_parse` chamar `_text_to_markdown`, `_detect_hyperlinks`, `_spell_check` antes de enviar ao LLM. | Centraliza pré‑processamento e garante que o LLM receba texto limpo e estruturado. | Atualizar fluxo em `analyze_cv` (ou endpoint equivalente) para usar a nova pipeline. |
| `backend/main.py` | **Prompt aprimorado** – substituir prompt atual por texto que indique: “Entrada em Markdown, preserve bullets, corrija capitalização, identifique links válidos, classifique níveis de habilidade”. | Direciona o modelo a usar a estrutura fornecida e a gerar saída mais precisa. | Modificar variável `SYSTEM_PROMPT` ou construção do `messages` antes da chamada OpenAI. |
| `backend/main.py` | **Validação pós‑extração** – checar presença de chaves obrigatórias (`personal`, `experience`, `education`, `skills`). Se faltar, chamar LLM novamente com prompt de preenchimento. | Garante que todas as seções estejam presentes. | Implementar função `validate_extracted_data(json_output)` que devolve boolean e lista de seções faltantes. |
| `backend/main.py` | **Cache temporário de Markdown** – armazenar Markdown gerado em `tempfile.NamedTemporaryFile(delete=False)` usando hash do PDF path. | Evita recomputação em chamadas repetidas ao mesmo PDF. | Ler cache antes de processar; se existir e não houver mudança no arquivo, reutilizar. |
| `backend/main.py` | **Teste unitário** – criar novo arquivo `tests/test_markdown_extraction.py` que verifica: <br>• Ordem correta de seções <br>• Detecção de bullets <br>• Validação de links <br>• Correção ortográfica | Garante que as novas funcionalidades funcionem como esperado. | Usar `pytest` e fixtures com PDFs curtos de exemplo. |
| `backend/requirements.txt` | Adicionar dependências: `pyspellchecker`, `validators`, `requests`. | Necessárias para novas funções. | Atualizar arquivo. |
| `backend/README.md` (opcional) | Documentar nova pipeline e instruções de uso. | Manutenção e onboarding. | Atualizar texto. |

## Suposições & Decisões
- O PDF tem menos de 10 páginas; a conversão para Markdown é suficiente para representar a estrutura. 
- Links são simples URLs; não será necessário lidar com links embutidos em imagens ou objetos. 
- Erros ortográficos são limitados a palavras isoladas; não será feita correção de gramática avançada. 
- O modelo LLM já está configurado (Analytics) e aceita prompts de até 8 k tokens. 
- O ambiente tem acesso à internet para validar hyperlinks via HEAD request; caso contrário, a validação será apenas sintática. 

## Passos de Verificação
1. Executar `pytest` e garantir que todos os novos testes passem. 
2. Submeter um PDF de exemplo (currículo da Milena) e conferir que o JSON retornado contém: 
   - Seções na ordem correta. 
   - Bullets preservados. 
   - Campo `links` com indicadores `valid: true/false`. 
   - Correções ortográficas aplicadas (ex.: “atuação” → “Atuação”). 
3. Verificar que o cache funciona (segundas chamadas são rápidas). 
4. Revisar logs para confirmar que a validação de links não gera exceções. 

## Próximos Passos
- Implementar as funções e integrações descritas. 
- Atualizar o prompt e a validação pós‑extração. 
- Criar os testes e atualizar `requirements.txt`. 
- Realizar a validação manual com PDFs reais. 

---
*Este plano está pronto para ser executado.*