import './globals.css';
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang='pt-BR' suppressHydrationWarning>
      <body className='bg-slate-950 text-white antialiased' suppressHydrationWarning>{children}</body>
    </html>
  )
}
