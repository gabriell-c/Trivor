import type { Metadata } from 'next'
import { Poppins } from 'next/font/google'
import './globals.css'
import AppShell from './components/AppShell'

/* Poppins como fonte principal do app — auto-hospedada pelo next/font
 * (sem CDN externo em runtime); a variável --font-poppins é consumida
 * no @theme do globals.css como --font-sans.
 * Pesos explícitos (400-700): 'variable' dispara "Font Poppins has no
 * definable axes" no build Turbopack deste Next. */
const poppins = Poppins({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  style: 'normal',
  variable: '--font-poppins',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Trivor - Inteligência de Currículos & Mercado',
  description: 'Diagnóstico ATS e análise de inteligência de mercado com IA',
  icons: {
    icon: [
      { url: '/favicon.png', type: 'image/png' }
    ],
    shortcut: '/favicon.png',
    apple: '/favicon.png',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  /* `children` é a página da rota atual (/dashboard, /analise-curriculo,
   * /analise-linkedin, /inteligencia-mercado, /candidaturas, /config-ias,
   * /logs) — o AppShell a envolve com a sidebar; a URL é a fonte da verdade. */
  return (
    <html lang="pt-BR" className={poppins.variable} suppressHydrationWarning>
      <body className="bg-[#070a12] text-white antialiased min-h-screen" suppressHydrationWarning>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  )
}
