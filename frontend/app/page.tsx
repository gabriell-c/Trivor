// A rota "/" é a entrada da shell Trivor: o RootLayout (layout.tsx) ignora
// `children` e renderiza só o AppShell (sidebar + ferramentas em tabs), então
// o conteúdo da rota nunca chega ao HTML. Este arquivo apenas reexporta a
// tool de CV real (CurriculoTool), mantendo a rota válida no build sem
// duplicar a UI antiga desta página (substituída pelas 5 features da tool).
export { default } from './components/CurriculoTool'
