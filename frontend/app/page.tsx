// A rota "/" abre o Dashboard — a página principal do app. Cada tool tem sua
// rota real em /<slug> (analise-curriculo, analise-linkedin,
// inteligencia-mercado, candidaturas, config-ias, logs); a sidebar
// (components/Layout.tsx) navega por URL via next/link.
export { default } from './dashboard/page'
