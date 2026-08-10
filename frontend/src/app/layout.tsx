import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { MarkaProvider } from '@/components/marka-provider';
import { markaZeSrodowiska } from '@/lib/marka';

const inter = Inter({ subsets: ['latin'] });

// Marka pochodzi ze zmiennych środowiskowych, więc strona musi powstawać przy żądaniu,
// a nie w czasie budowy obrazu — inaczej ten sam obraz nie obsłużyłby dwóch wdrożeń.
export const dynamic = 'force-dynamic';

export function generateMetadata(): Metadata {
  const marka = markaZeSrodowiska();
  return {
    title: `${marka.nazwa} - System zarządzania dokumentami`,
    description: marka.opis,
    // Ikona MUSI iść przez metadane, nie przez pliki `app/icon.png` i `app/favicon.ico`.
    // Te konwencje Next.js wstrzykują jeden, ten sam plik do KAŻDEGO wdrożenia — przez
    // co demo HiRS pokazywało w karcie przeglądarki ikonę „DM" należącą do ZCO.
    // Ścieżki przychodzą ze zmiennych środowiskowych, jak reszta marki.
    icons: { icon: marka.ikona, apple: marka.ikonaApple },
  };
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const marka = markaZeSrodowiska();
  // Kolory jadą jako zmienne CSS: klasy Tailwinda są ustalane w czasie budowy, więc
  // wartość koloru musi wejść do drzewa stylów, a nie do nazwy klasy.
  const zmienneKoloru = {
    '--marka-tlo': marka.tlo,
    '--marka-akcent': marka.akcent,
    '--marka-naglowek': marka.naglowek,
  } as React.CSSProperties;

  return (
    <html lang="pl" style={zmienneKoloru}>
      <body className={inter.className}>
        <MarkaProvider marka={marka}>{children}</MarkaProvider>
      </body>
    </html>
  );
}
