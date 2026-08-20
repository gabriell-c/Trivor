import type { Metadata } from 'next'
import './globals.css'
import AppShell from './components/AppShell'

export const metadata: Metadata = {
  title: 'Trivor - Inteligência de Currículos & Mercado',
  description: 'Diagnóstico ATS e análise de inteligência de mercado com IA',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className="bg-[#070a12] text-white antialiased min-h-screen" suppressHydrationWarning>
        <AppShell />
      </body>
    </html>
  )
}
