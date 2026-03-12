import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Quant Agent v2.1 -- Public Edition',
  description: 'Multi-strategy AI trading system with regime-aware risk management, confidence calibration, and quantitative portfolio construction.',
  openGraph: {
    title: 'Quant Agent v2.1 -- Public Edition Dashboard',
    description: 'Regime-aware multi-sleeve trading agent with Claude AI integration. Simulated demo with paper-traded performance.',
    type: 'website',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
