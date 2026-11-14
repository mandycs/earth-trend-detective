import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Earth Trend Detective',
  description:
    'Pick a place, see what is changing there, whether the change is real, and how much of it the climate does not explain.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
