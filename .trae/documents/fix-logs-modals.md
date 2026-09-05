# Plano: Corrigir Logs dos Modais - Texto Extraído e Prompt LLM

## Resumo
Corrigir o problema crítico onde os modais dos logs não mostravam informação alguma sobre texto extraído e prompt enviado à LLM.

## Problema Identificado

### Causa Raiz
1. **Servidor rodando código antigo** — O servidor estava iniciado com `python main.py` (sem uvicorn), que carregou o código ANTES da correção do middleware skip ser aplicada.
2. **Middleware não estava pulando `/api/cv/analyze`** — Como o servidor rodava código antigo, o middleware criava um log vazio para CADA requisição CV, além do log completo criado pela função `analyze_cv`.
3. **Logs antigos saturavam a lista** — 1508 logs vazios de `/api/cv/analyze` apareciam antes dos logs com dados, pois eram ordenados por timestamp DESC.

### Evidência
- Antes da correção: 1557 logs CV, apenas 49 com dados (3% tinham extracted_text/llm_prompt)
- Depois da correção: 1 log CV, 1 com dados (100%)

## Mudanças Já Aplicadas (código fonte)

### 1. Backend — `backend/main.py`
- **Middleware skip** (linha 361-363): Pula logging para `/api/cv/analyze`
- **Log com dados completos** (linha 627-637): Salva `extracted_text`, `llm_prompt`, `response_summary`

### 2. Backend — `backend/logging_service.py`
- **Schema atualizado**: Colunas `extracted_text TEXT` e `llm_prompt TEXT` adicionadas
- **Função `log_request`**: Aceita novos parâmetros

### 3. Frontend — `frontend/app/logs/page.tsx`
- **Estado `showRawText`**: Toggle para mostrar/ocultar texto
- **Seção "Texto Extraído & Prompt LLM"**: Exibe ambos com botões de copiar
- **Ícone `FileText`**: Importado do lucide-react

### 4. Frontend — `frontend/app/types/analysis.ts`
- **Interface `LogEntry`**: Campos `extracted_text` e `llm_prompt` adicionados

## Correções Executadas (runtime)

1. **Servidor reiniciado** com uvicorn (código novo):
   - Velho: PID 11772, `python main.py` (código antigo)
   - Novo: PID 26372, `uvicorn main:app --host 127.0.0.1 --port 8008` (código novo)

2. **Logs antigos limpos**:
   - 1508 logs vazios de `/api/cv/analyze` removidos
   - Banco agora tem apenas logs com dados relevantes

3. **Teste de validação**:
   - Análise CV de teste rodou com sucesso
   - Log criado: extracted_text=574 chars, llm_prompt=4998 chars, response_summary=5285 chars
   - Sem duplicação de logs

## Estado Atual

- ✅ Servidor rodando em `http://127.0.0.1:8008`
- ✅ Middleware skip funcionando (sem duplicação)
- ✅ Logs salvos com extracted_text, llm_prompt, response_summary
- ✅ Frontend preparado para exibir os dados
- ✅ Banco de dados limpo (sem logs vazios)

## Próximos Passos (apenas se necessário)

1. **Testar no frontend** — Abrir página de logs e verificar se o modal mostra o botão "Ver texto extraído"
2. **Fazer commit** das alterações do código-fonte
3. **Verificar se o servidor permanece rodando** após o teste

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `backend/main.py` | Middleware skip + log com dados completos |
| `backend/logging_service.py` | Schema + função log_request atualizados |
| `frontend/app/logs/page.tsx` | Seção "Texto Extraído & Prompt LLM" no modal |
| `frontend/app/types/analysis.ts` | Interface LogEntry atualizada |

## Verificação

Para verificar se está funcionando:
1. Abrir `http://127.0.0.1:8008/api/logs?limit=5` — deve mostrar logs com `extracted_text` e `llm_prompt`
2. Abrir frontend → página de logs → clicar em um log CV → modal deve mostrar botão "Ver texto extraído"
