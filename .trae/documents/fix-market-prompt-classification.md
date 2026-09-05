# Plano: Reescrever prompts de extração de vagas — Foco em classificação correta

## Problema
A IA continua classificando benefícios (Auxílio Educação, Plano de Saúde), modalidades (Home Office Flexível) e processos (Code Review, Pair Programming) como "requirements" (habilidades obrigatórias). Os prompts atuais são muito longos e a regra anti-pattern não está na posição de maior impacto cognitivo.

## Abordagem
1. **Encurtar drasticamente** — prompts longos diluem as regras críticas
2. **Decision tree no início** — fluxo de 3 perguntas simples para classificação
3. **Anti-pattern como ÚLTIMA instrução** — efeito recency: a última coisa que a IA lê é o que mais influencia
4. **Manter foco conceitual** — sem listas fixas de palavras

## Arquivo: `backend/market_service.py`

### Alteração 1: Prompt `extract_job_with_ai` (linha ~796)

**Atual**: ~65 linhas de regras conceituais + anti-patterns espalhados
**Novo**: ~35 linhas, estrutura:
```
1. Role (1 linha)
2. Decision tree (3 perguntas em 3 linhas)
3. Definições das 5 categorias (breve, 1 linha cada)
4. [REGRAS DE RELEVÂNCIA]
5. [ANTI-PATTERN — ÚLTIMA COISA antes do JSON] ← posição de maior impacto
6. JSON format
```

### Alteração 2: Prompt `extract_jobs_batched` (linha ~982)
Mesma estrutura, adaptado para múltiplas vagas.

### Alteração 3: Adicionar verificação pós-extração
Após a IA retornar os dados, adicionar uma função `_sanitize_requirements` que:
- Remove termos óbvios de benefícios/modalidades do array `requirements` via heuristicas simples
- Isso como fallback de segurança, não como solução principal

## Decisões
- Não criar lista fixa de palavras proibidas — manter enfoque conceitual
- Manter o `_parse_batch_response` atual (já corrigido)
- Manter o `_batch_mismatch_warned` (já corrigido)

## Verificação
1. Syntax check do Python
2. Executar análise de mercado com query real
3. Confirmar que benefícios e modalidades não aparecem em required_technologies
4. Confirmar que soft skills são razoavelmente extraídas
