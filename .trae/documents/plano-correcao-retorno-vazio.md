# Plano de Resolução: Correção de Retorno Vazio na Análise de Mercado

## Análise da Causa Raiz

Após investigar o fluxo do backend (`market_service.py` e `main.py`) e do frontend (`app/market/page.tsx`), identificamos os seguintes motivos para o resultado "completo vazio":

1. **JSearch API Rate-Limit / Timeout Silencioso**:
   - Quando as chaves JSearch atingem o limite de taxa (HTTP 429/504), a função `_fetch_jsearch_jobs` retorna lista vazia `[]`.
   - O banco de dados SQLite `market_raw_jobs` fica sem registros (`total_jobs = 0`).
   - O backend retorna um relatório zerado sem informar o motivo ao usuário, e o frontend exibe telas/estatísticas zeradas ("retornou absolutamente nada").

2. **Falta de Feedback no Frontend sobre Diagnóstico da Busca**:
   - Se o backend vasculhar 0 vagas reais (devido a chaves esgotadas ou sem vagas no parâmetro temporal), o usuário só vê 0s e uma aba de resultados em branco.
   - O frontend precisa exibir alertas informando quando a API de busca de vagas falhar ou quando as chaves fornecidas estiverem esgotadas/inválidas.

3. **Resiliência e Tolerância a Falhas na Busca JSearch**:
   - Se todas as chaves JSearch falharem com rate limit/timeout, o sistema deve registrar e informar explicitamente qual chave ou status causou a falha, além de tratar retries com backoff.
   - Garantir que buscas com termos abrangentes (multi-query) façam fallback ou ampliem o escopo de busca caso o primeiro termo específico traga 0 resultados.

---

## Modificações Propostas

### 1. Backend (`backend/market_service.py` e `backend/main.py`)
- **Status do Diagnóstico da Busca JSearch**: Retornar no dicionário do `report` informações sobre o status da busca JSearch (`jsearch_status`: "ok", "rate_limit_exceeded", "no_jobs_found", "no_keys").
- **Melhoria no Multi-Query Fallback**: Se a busca exata (ex: "enfermeiro") retornar poucas ou 0 vagas na JSearch, expandir automaticamente para termos relacionados (ex: "enfermagem", "auxiliar de enfermagem", "saúde") ou flexibilizar o parâmetro de data no fallback para garantir amostragem de dados.
- **Detecção e Notificação de Rate-Limit**: Se todas as chaves falharem por 429/504, registrar no `report` para que a API retorne um aviso amigável em vez de um relatório vazio.

### 2. Frontend (`frontend/app/market/page.tsx`)
- **Alerta de Diagnóstico de Vagas**: Exibir uma banner de aviso se `total_jobs_scanned == 0` explicando a causa (ex: "As chaves JSearch atingiram o limite de chamadas ou a API está temporariamente instável. Tente novamente mais tarde ou adicione novas chaves nas configurações.").
- **Feedback de Vagas Encontradas x Analisadas**: Mostrar claramente quantas vagas foram coletadas na API JSearch e quantas passaram no pré-filtro.

---

## Passos para Verificação

1. Executar teste automatizado simulando buscas com termos específicos ("enfermeiro", "desenvolvedor", "analista").
2. Simular falha/rate limit de chaves JSearch para verificar se a API retorna o status correto de erro em vez de tela vazia.
3. Testar via frontend a submissão do formulário de análise e verificar a exibição de avisos e resultados.
