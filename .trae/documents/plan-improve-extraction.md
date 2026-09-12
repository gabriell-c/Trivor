# Plano: Melhorar Extração de Skills pela IA

## Resumo
A IA está extraindo muito poucos requisitos das vagas (ex: "Pacote Office" e "Excel" aparecem em apenas 2 de 67 vagas de assistente administrativo). O problema é o prompt excessivamente restritivo e exemplos tech-focused que enviesam a IA.

## Análise do Estado Atual

### Prompt atual (linha 1258-1322)
- Exemphos tech-focused: "Python", "React", "AWS", "PMP"
- Instrução restritiva: "É um CONHECIMENTO/FERRAMENTA que a pessoa PRECISA TER?"
- IA filtra agressivamente itens comuns como "Pacote Office", "Excel", "Ensino Médio"
- O campo `requirements` só aceita "conhecimento técnico, ferramentas, linguagens, idiomas, formação acadêmica" — mas a IA interpreta "técnico" de forma restrita

### Fallback (linha 1210-1231)
- Só é acionado quando `not result or not result.get("requirements")`
- Se a IA retornar 1-2 requisitos (muito poucos), o fallback NÃO é acionado

### `_sanitize_requirements` (linha 1036-1077)
- Remove benefícios, modalidade, processos, experiência
- Pode estar removendo itens legítimos por match de substring

## Mudanças Propostas

### 1. Rewriting do Prompt de Extração em Lote (batch)
**Arquivo**: `backend/market_service.py`, linhas ~1258-1322

**O que mudar**:
- Remover a pergunta restritiva "PRECISA TER"
- Adicionar exemplos diversificados (admin, vendas, saúde, etc.)
- Instruir explicitamente para extrair TUDO que a vaga menciona como requisito/qualificação
- Adicionar seção "O QUE EXTRAIR" com lista explícita de tipos de skills

**Novo prompt**:
```
EXTRAÇÃO DE DADOS — seja O MAIS COMPLETO POSSÍVEL.

Para CADA vaga, extraia TODOS os requisitos, qualificações e competências mencionados.

EXEMPLOS DO QUE CONTAR COMO "requirements":
- Tech: Python, Java, React, SQL, Excel avançado
- Office: Pacote Office, Word, Excel, PowerPoint, Google Sheets
- Idiomas: Inglês intermediário, Espanhol avançado, Francês básico
- Formação: Ensino Médio, Superior completo, Cursando administração
- Soft: Comunicação, trabalho em equipe, proatividade, organização
- Certificações: OAB, CREFITO, PMP, AWS, NBR 16362
- Experiência: Gestão de contratos, elaboração de editais, controle financeiro

NÃO é skill (não colocar em requirements):
- Benefícios da empresa (vale transporte, plano de saúde, Gympass)
- Modalidade (remoto, híbrido, presencial)
- Responsabilidades/do dia a dia (atender telefone, organizar arquivos)
- Anos de experiência (vai para exp_years_min/max)

FORMATO JSON:
[{{
  "is_relevant": true|false,
  "rejection_reason": "string|null",
  "role_level": "Júnior"|"Pleno"|"Sênior"|"Especialista"|null,
  "exp_years_min": número|null,
  "exp_years_max": número|null,
  "requirements": ["Excel intermediário", "Pacote Office", "Inglês básico"],
  "nice_to_have": ["Conhecimento em SAP"],
  "certifications": ["OAB"],
  "soft_skills": ["organização", "proatividade"],
  "salary_min": número|null,
  "salary_max": número|null,
  "currency": "BRL"|"USD"|null
}}]
```

### 2. Rewriting do Prompt Individual (single job)
**Arquivo**: `backend/market_service.py`, linhas ~960-1009

Mesma abordagem do item 1, adaptada para vaga única.

### 3. Melhorar Fallback — Acionar quando requisitos são escassos
**Arquivo**: `backend/market_service.py`, linha 1227

Mudar de:
```python
if not result or not result.get("requirements"):
```
Para:
```python
if not result or len(result.get("requirements", [])) < 2:
```

Assim, se a IA retornar apenas 0-1 requisitos (claramente insuficiente), o fallback heurístico é acionado.

### 4. Melhorar Fallback Heurístico — Extrair mais patterns
**Arquivo**: `backend/market_service.py`, linhas 611-650

Expandir os patterns do `heuristic_extract` para capturar:
- Linhas após "Requisitos:", "Requisitos:", "Obrigatório:"
- Linhas após "Formação:", "Escolaridade:"
- Linhas após "Idioma:", "Idiomas:"
- Termos comuns: "Pacote Office", "Excel", "Word", "Informática", "Inglês", etc.

### 5. Revisar `_sanitize_requirements`
**Arquivo**: `backend/market_service.py`, linhas 1036-1077

- Verificar se os patterns estão muito agressivos
- Adicionar exceções para termos legítimos que possam ser capturados erroneamente

## Verificação
1. Rodar análise de "Assistente Administrativo" com a nova chave JSearch
2. Verificar se "Pacote Office", "Excel", "Informática" aparecem em múltiplas vagas
3. Verificar se idiomas (Inglês, Espanhol) são extraídos corretamente
4. Verificar se formação escolar é extraída
5. Confirmar que o fallback heurístico complementa quando a IA falha

## Arquivos Modificados
- `backend/market_service.py` — prompts, fallback, sanitização
