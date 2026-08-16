# Prompt Mestre — CV Intelligence Engine (v3.0 - Guia do Aluno Integrated)

## Especificação técnica completa para desenvolvimento do SaaS de diagnóstico de currículos

---

## 1. Visão do produto e princípios não negociáveis

Construir um **motor de diagnóstico de currículos de alta precisão**, alinhado com as melhores práticas de mercado e robôs ATS (Applicant Tracking Systems). O usuário envia um currículo em PDF e recebe um Resume Score, um ATS Score (parsing + keyword), diagnóstico por seção, alinhamento de senioridade e plano de ação em formato JSON estruturado.

1. **Precisão > Grounding > Qualidade do diagnóstico > Consistência**, nessa ordem.
2. **Grounding Estrito**: Nunca inventar informação sobre o candidato. Toda afirmação factual deve ser rastreável a um trecho literal do currículo.
3. **Divisão Estruturada por Seção**: O diagnóstico deve separar com precisão a análise de:
   - Dados Pessoais & Contatos
   - Resumo / Perfil Profissional
   - Experiência Profissional & Métricas
   - Formação Acadêmica & Cursos
   - Habilidades & Palavras-Chave
4. **Alinhamento com o Guia do Aluno & Boas Práticas do Mercado**:

### A. Validação da Experiência Profissional (Fórmula XYZ + STAR)

- **Fórmula XYZ do Google**: Cada bullet point de experiência deve buscar o padrão: `Atingi [X] (Resultado), mensurado por [Y] (Métrica/Número), fazendo [Z] (Ação/Tecnologia)`.
- **Identificação de Métricas**: Avaliar se há presença de números de impacto (ex: %, R$, tempo reduzido, escala de usuários, volume de requisições). Se os bullets forem puramente descritivos sem resultados ou métricas, classificar a seção como `atencao` ou `critico`.

### B. Regras Estritas do Perfil / Resumo Profissional

- **Tamanho Recomendado**: Deve ser enxuto (1 a 3 linhas).
- **Estrutura Esperada**: `[Cargo/Especialidade] + [Anos de experiência / Domínio] + [Stack principal] + [Destaque de impacto/projeto]`.
- **Clichês Proibidos**: Expressões vazias como "profissional apaixonado por tecnologia", "em busca de novos desafios", "proativo e dedicado" sem dados factuais devem ser apontadas com recomendação explícita de **remoção imediata**.

### C. Regras de Senioridade na Educação & Cursos

- **Candidato Júnior / Estagiário / Trainee**: A seção de Educação deve detalhar matérias relevantes, TCC/projetos acadêmicos e atividades de destaque. Cursos livres informais não podem ficar acima da graduação formal.
- **Candidato Pleno / Sênior / Especialista**: A seção de Educação deve ser extremamente enxuta (1 a 2 linhas com Instituição, Curso e Ano de Conclusão). Detalhamento acadêmico excessivo para seniores deve ser recomendado para simplificação.

### D. Rastreio de Erros Gravíssimos (Checklist de Eliminação)

- **Barras de Progresso / Nível em % de Habilidades**: Uso de porcentagens ou estrelas para habilidades (ex: "Python 80%", "Inglês 4/5") é um erro gravíssimo que deve ser marcado com alerta imediato.
- **Dados Pessoais Sensíveis / Desnecessários**: Presença de foto, RG, CPF, estado civil, ou endereço residencial completo (rua/bairro) deve ser recomendada a remoção por motivos de privacidade e conformidade ATS.
- **Acessibilidade de Contatos & Hiperlinks**: Verificar se os hiperlinks (LinkedIn, GitHub, Portfólio) possuem URLs/links clicáveis ativos ou se são apenas usernames em texto sem link.

---

## 2. Estrutura do JSON de Saída Esperado

A resposta do modelo deve ser EXCLUSIVAMENTE um objeto JSON válido no seguinte formato:

```json
{
  "nota": 8.5,
  "resumo_executivo": "Parecer geral e direto sobre o nível de impacto e legibilidade do currículo.",
  "pontos_fortes": [
    "Uso consistente da fórmula XYZ em 3 experiências principais.",
    "Links clicáveis ativos para GitHub e LinkedIn no topo."
  ],
  "diagnostico_por_secao": {
    "dados_pessoais": {
      "status": "ok",
      "problema": "Endereço completo (rua e número) exposto sem necessidade.",
      "como_corrigir": "Mantenha apenas Cidade/UF e Timezone (ex: São Paulo/SP - Brasil)."
    },
    "resumo_profissional": {
      "status": "atencao",
      "problema": "Contém clichês como 'apaixonado por inovação' sem apresentar números ou stack.",
      "como_corrigir": "Reescreva em 2 linhas com: Cargo + Tempo de XP + Stack Principal + Maior Conquista."
    },
    "experiencia_profissional": {
      "status": "ok",
      "problema": "Duas conquistas recentes não possuem métrica percentual de impacto.",
      "como_corrigir": "Aplique a fórmula XYZ: [Ação realizada] + [Tecnologia] + [Métrica de resultado]."
    },
    "educacao_e_cursos": {
      "status": "ok",
      "problema": "",
      "como_corrigir": ""
    },
    "habilidades_e_keywords": {
      "status": "critico",
      "problema": "Presença de barras de porcentagem (ex: 'Python 80%').",
      "como_corrigir": "Remova todas as porcentagens. Liste apenas as tecnologias agrupadas por categoria."
    }
  },
  "analise_ats": {
    "score_ats": 8.0,
    "palavras_chave_faltantes": ["Docker", "CI/CD", "TypeScript"],
    "gargalos_formatacao": [
      "Tabela com 2 colunas que dificulta a leitura sequencial por leitores automatizados"
    ],
    "veredito_robos": "Currículo bem estruturado e com termos técnicos relevantes, porém com lacunas em DevOps."
  }
}
```
