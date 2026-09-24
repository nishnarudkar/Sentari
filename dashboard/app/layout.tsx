import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Sentari — earnings & filings intelligence",
  description: "Aspect-level sentiment on earnings calls and filings, with every claim traceable to its source sentence.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav>
          <div className="wrap">
            <Link href="/" className="brand">Sentari</Link>
            <Link href="/">Watchlist</Link>
            <Link href="/drift">Drift monitor</Link>
            <Link href="/models">Models</Link>
            <span className="spacer" />
            <span className="muted small nav-note">research tool · not investment advice</span>
          </div>
        </nav>
        <div className="wrap">
          {children}
          <div className="disclaimer">
            Sentari is a research and decision-support tool built for a university project. Nothing shown here is investment
            advice, a recommendation, or a prediction of price movements. Sample data may be synthetic.
          </div>
        </div>
      </body>
    </html>
  );
}
