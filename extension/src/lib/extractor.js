/**
 * Trivor — LinkedIn Profile Exporter
 * Extrator resiliente multi-idioma (PT-BR, EN, ES)
 *
 * Estratégia:
 * - Prioriza leitura do DOM com seletores semanticamente estáveis por texto de
 *   heading, aria-label e data-* — evitando classes CSS frágeis que mudam.
 * - Suporta inglês, português e espanhol através de dicionários de labels.
 * - Expande seções recolhidas ("ver mais", "ver todos") automaticamente.
 * - Não faz scraping em massa: apenas exporta o perfil do usuário logado.
 * - 100% client-side: usa a sessão autenticada e o DOM da página atual.
 */

"use strict";

// ---------------------------------------------------------------------------
// 1. Dicionários de labels por idioma
// ---------------------------------------------------------------------------
const SECTIONS = [
  {
    key: "contact",
    labels: {
      pt: ["informações de contato", "contato"],
      en: ["contact info", "contact"],
      es: ["información de contacto", "contacto"],
    },
  },
  {
    key: "about",
    labels: {
      pt: ["sobre", "resumo", "about"],
      en: ["about"],
      es: ["acerca de", "sobre", "resumen"],
    },
  },
  {
    key: "activity",
    labels: {
      pt: ["atividade recente", "atividade"],
      en: ["activity"],
      es: ["actividad"],
    },
  },
  {
    key: "experience",
    labels: {
      pt: ["experiências", "experiência"],
      en: ["experience"],
      es: ["experiencia", "experiencias"],
    },
  },
  {
    key: "education",
    labels: {
      pt: ["formação acadêmica", "formação", "educação"],
      en: ["education"],
      es: ["formación", "educación"],
    },
  },
  {
    key: "certifications",
    labels: {
      pt: ["licenças e certificações", "certificações", "licenças"],
      en: ["licenses and certifications", "certifications", "licenses"],
      es: ["licencias y certificaciones", "certificaciones"],
    },
  },
  {
    key: "projects",
    labels: { pt: ["projetos"], en: ["projects"], es: ["proyectos"] },
  },
  {
    key: "courses",
    labels: { pt: ["cursos"], en: ["courses"], es: ["cursos"] },
  },
  {
    key: "skills",
    labels: {
      pt: ["competências e soft skills", "competências", "habilidades"],
      en: ["skills", "competencies"],
      es: ["aptitudes", "competencias"],
    },
  },
  {
    key: "languages",
    labels: { pt: ["idiomas"], en: ["languages"], es: ["idiomas"] },
  },
  {
    key: "interests",
    labels: { pt: ["interesses"], en: ["interests"], es: ["intereses"] },
  },
  {
    key: "volunteer",
    labels: {
      pt: ["voluntariado", "trabalho voluntário"],
      en: ["volunteer experience", "volunteering"],
      es: ["voluntariado", "experiencia de voluntariado"],
    },
  },
  {
    key: "publications",
    labels: {
      pt: ["publicações"],
      en: ["publications"],
      es: ["publicaciones"],
    },
  },
  {
    key: "recommendations",
    labels: {
      pt: ["recomendações"],
      en: ["recommendations"],
      es: ["recomendaciones"],
    },
  },
  {
    key: "honors",
    labels: {
      pt: ["prêmios e honrarias", "honrarias", "prêmios"],
      en: ["honors and awards", "honors", "awards"],
      es: ["premios y honores", "premios"],
    },
  },
  {
    key: "organizations",
    labels: {
      pt: ["organizações"],
      en: ["organizations"],
      es: ["organizaciones"],
    },
  },
  {
    key: "featured",
    labels: { pt: ["destaques"], en: ["featured"], es: ["destacados"] },
  },
];

const EXPAND_LABELS = {
  pt: [
    "mostrar mais",
    "ver todos",
    "ver tudo",
    "ver mais",
    "expandir",
    "mostrar tudo",
  ],
  en: ["show more", "see all", "view all", "show all", "expand", "more"],
  es: ["mostrar más", "ver todo", "ver todos", "ampliar", "expandir", "más"],
};

// ---------------------------------------------------------------------------
// 2. Utilidades de DOM
// ---------------------------------------------------------------------------
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

function cleanText(str = "") {
  return (str || "").replace(/\s+/g, " ").trim();
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Remove nós irrelevantes e retorna texto limpo. */
function getNodeText(node) {
  if (!node) return "";
  const clone = node.cloneNode(true);
  $$("script,style,noscript,svg", clone).forEach((el) => el.remove());
  return cleanText(clone.innerText || clone.textContent || "");
}

// ---------------------------------------------------------------------------
// 3. Detecção de idioma
// ---------------------------------------------------------------------------
function detectLang(doc = document) {
  const lang = (doc.documentElement.lang || "").toLowerCase();
  if (lang.startsWith("pt")) return "pt";
  if (lang.startsWith("es")) return "es";
  if (lang.startsWith("en")) return "en";

  const text = ((doc.body && doc.body.innerText) || "")
    .slice(0, 4000)
    .toLowerCase();
  if (/\b(sobre|formação|experiência|idiomas|competências)\b/.test(text))
    return "pt";
  if (/\b(acerca de|formación|experiencia|aptitudes)\b/.test(text)) return "es";
  return "en";
}

// ---------------------------------------------------------------------------
// 4. Expansão automática de seções recolhidas
// ---------------------------------------------------------------------------
async function clickExpandAll(doc = document) {
  const lang = detectLang(doc);
  const labels = EXPAND_LABELS[lang] || EXPAND_LABELS.en;
  let clicked = 0;

  for (let round = 0; round < 15; round++) {
    let foundInRound = false;

    // Botões com texto de expansão
    const buttons = $$("button", doc).filter((b) => {
      if (b.disabled) return false;
      const t = cleanText(b.innerText || "").toLowerCase();
      return labels.some((lab) => t === lab || t.includes(lab));
    });
    for (const btn of buttons) {
      try {
        btn.click();
        clicked++;
        foundInRound = true;
        await sleep(100);
      } catch {}
    }

    // Elementos aria-expanded colapsados
    const collapsed = $$('[aria-expanded="false"]', doc);
    for (const el of collapsed) {
      const role = el.getAttribute("role") || "";
      const label = (el.getAttribute("aria-label") || "").toLowerCase();
      if (role === "button" && /(mais|all|more|todos|expand)/.test(label)) {
        try {
          el.click();
          clicked++;
          foundInRound = true;
          await sleep(80);
        } catch {}
      }
    }

    if (!foundInRound || clicked > 80) break;
  }
  // Dá tempo para o LinkedIn renderizar o conteúdo recém-expandido.
  await sleep(600);
  return clicked;
}

// ---------------------------------------------------------------------------
// 5. Localização de seções por label (resiliente a classes)
// ---------------------------------------------------------------------------
function findSection(key, doc = document) {
  const lang = detectLang(doc);
  const sectionDef = SECTIONS.find((s) => s.key === key);
  if (!sectionDef) return null;
  const labels = sectionDef.labels[lang] || sectionDef.labels.en;

  // 1) Headings / elementos com aria-label que correspondam
  const candidates = $$(
    "section, div[data-testid], div[id], h2, h3, span[aria-label]",
    doc,
  );
  for (const el of candidates) {
    const text = cleanText(
      el.innerText || el.getAttribute("aria-label") || "",
    ).toLowerCase();
    if (!text || text.length > 300) continue;
    if (
      labels.some(
        (lab) => text === lab || text.startsWith(lab) || text.includes(lab),
      )
    ) {
      // Retorna a seção <section> mais próxima (ou o próprio container)
      return el.closest("section") || el.closest("div") || el;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// 6. Parsing de experiências (resiliente)
// ---------------------------------------------------------------------------
function parseExperiences(secNode) {
  const out = [];
  // Tenta lista de itens li dentro da seção.
  const items = $$("li", secNode).slice(0, 40);
  for (const li of items) {
    const text = getNodeText(li);
    if (text.length < 3) continue;
    // Heurística de título vs corpo: primeiro 'div' com texto em negrito/pseudo.
    out.push({ texto_bruto: text });
  }
  // Fallback: se não houver <li>, captura o texto geral da seção.
  if (out.length === 0) {
    const full = getNodeText(secNode);
    if (full) out.push({ texto_bruto: full });
  }
  return out;
}

// ---------------------------------------------------------------------------
// 7. Extrator principal via DOM
// ---------------------------------------------------------------------------
function extractProfileFromDom(doc = document) {
  const lang = detectLang(doc);

  const profile = {
    fonte: "linkedin_extensao_trivor",
    api: "manual_exportacao",
    url: typeof location !== "undefined" ? location.href : "",
    idioma_detectado: lang,
    extraido_em: new Date().toISOString(),
    dados: {},
  };

  // Nome — prioriza h1 no topo do perfil
  const nameEl = $("h1, .text-heading-xlarge", doc);
  profile.dados.nome = nameEl ? cleanText(nameEl.innerText) : "";

  // Headline
  const headlineEl = $(
    ".text-body-medium.break-words, [data-generated-suggestion-target]",
    doc,
    "headline",
  );
  profile.dados.headline = headlineEl ? cleanText(headlineEl.innerText) : "";

  // Localização
  const locEl = $(
    '.text-body-small.inline.t-black--light, span[data-testid="address"]',
    doc,
  );
  profile.dados.localizacao = locEl ? cleanText(locEl.innerText) : "";

  // Para cada seção mapeada, tenta extrair
  for (const sectionDef of SECTIONS) {
    const label = sectionDef.labels[lang] || sectionDef.labels.en;
    const secNode = findSection(sectionDef.key, doc);
    if (secNode) {
      profile.dados[sectionDef.key] = getNodeText(secNode);
    } else {
      profile.dados[sectionDef.key] = "";
    }
  }

  // Experiências estruturadas
  const expNode = findSection("experience", doc);
  profile.dados.experiencias_detalhadas = expNode
    ? parseExperiences(expNode)
    : [];

  return profile;
}

// ---------------------------------------------------------------------------
// 8. Exportação de JSON e Markdown
// ---------------------------------------------------------------------------
function toJSON(data, pretty = true) {
  return pretty ? JSON.stringify(data, null, 2) : JSON.stringify(data);
}

function toMarkdown(profile) {
  const d = profile.dados || {};
  const lines = [];
  lines.push("# Perfil exportado via Trivor");
  lines.push("");
  lines.push(`- **Fonte:** ${profile.fonte}`);
  lines.push(`- **Idioma detectado:** ${profile.idioma_detectado}`);
  lines.push(`- **Extraído em:** ${profile.extraido_em}`);
  lines.push("");
  if (d.nome) {
    lines.push(`## ${d.nome}`);
    lines.push("");
  }
  if (d.headline) {
    lines.push(`**Headline:** ${d.headline}`);
    lines.push("");
  }
  if (d.localizacao) {
    lines.push(`**Localização:** ${d.localizacao}`);
    lines.push("");
  }

  if (d.about) {
    lines.push("## Sobre");
    lines.push("");
    lines.push(d.about);
    lines.push("");
  }
  if (
    Array.isArray(d.experiencias_detalhadas) &&
    d.experiencias_detalhadas.length
  ) {
    lines.push("## Experiências");
    lines.push("");
    d.experiencias_detalhadas.forEach((e) => {
      lines.push(`- ${e.texto_bruto}`);
    });
    lines.push("");
  }
  for (const key of [
    "education",
    "certifications",
    "projects",
    "courses",
    "skills",
    "languages",
    "volunteer",
    "publications",
    "organizations",
    "honors",
    "recommendations",
    "featured",
    "activity",
    "interests",
  ]) {
    const val = d[key];
    if (val && typeof val === "string" && val.trim()) {
      const title =
        key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, " ");
      lines.push(`## ${title}`);
      lines.push("");
      lines.push(val);
      lines.push("");
    }
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// 9. API pública
// ---------------------------------------------------------------------------
const TrivorExtractor = {
  detectLang,
  clickExpandAll,
  extractProfileFromDom,
  toJSON,
  toMarkdown,
  cleanText,
};

if (typeof module !== "undefined") module.exports = TrivorExtractor;
