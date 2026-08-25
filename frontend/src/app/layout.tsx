import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import './globals.css';
import { LocaleProvider } from '@/components/locale-provider';
import { MarkaProvider } from '@/components/marka-provider';
import { enabledLocales } from '@/i18n/locales';
import { markaAktualna } from '@/lib/marka';

const inter = Inter({ subsets: ['latin'] });

// Marka pochodzi ze zmiennych środowiskowych, więc strona musi powstawać przy żądaniu,
// a nie w czasie budowy obrazu — inaczej ten sam obraz nie obsłużyłby dwóch wdrożeń.
export const dynamic = 'force-dynamic';

export async function generateMetadata(): Promise<Metadata> {
  const marka = await markaAktualna();
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

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const marka = await markaAktualna();
  // Kolory jadą jako zmienne CSS: klasy Tailwinda są ustalane w czasie budowy, więc
  // wartość koloru musi wejść do drzewa stylów, a nie do nazwy klasy.
  const zmienneKoloru = {
    '--marka-tlo': marka.tlo,
    '--marka-akcent': marka.akcent,
    '--marka-naglowek': marka.naglowek,
  } as React.CSSProperties;

  // Język i teksty czytamy TU, w komponencie serwerowym, i podajemy w dół tak samo
  // jak markę. Dzięki temu właściwy tekst jest w HTML-u już przy pierwszym renderze
  // — bez mignięcia polskiego napisu przed przełączeniem na angielski po hydratacji.
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    // `lang` musi iść za wyborem: to z niego korzystają czytniki ekranu przy doborze
    // głosu i przeglądarka przy propozycji tłumaczenia strony.
    <html lang={locale} style={zmienneKoloru}>
      <body className={inter.className}>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <LocaleProvider locales={enabledLocales()}>
            <MarkaProvider marka={marka}>{children}</MarkaProvider>
          </LocaleProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
