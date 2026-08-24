# Landing page HiRS

Strona sprzedażowa HiRS do wgrania na hosting z PHP, razem z podstroną
„Zamów dostęp do demo”, która wysyła zgłoszenia na **hirs@polmedi.com**.

Treść jest przeniesiona z prezentacji ([`../prezentacja-hirs`](../prezentacja-hirs)) —
te same argumenty, ta sama paleta, te same makiety ekranów z **wymyślonymi danymi**.

## Pliki

| Plik | Rola |
|---|---|
| `index.html` | strona główna |
| `demo.php` | podstrona z formularzem **i** jego obsługa |
| `smtp.php` | wysyłka poczty przez SMTP (bez bibliotek zewnętrznych) |
| `konfiguracja.php` | **jedyny plik do edycji po wgraniu** |
| `styl.css` | style obu stron |
| `.htaccess` | blokada dostępu do plików `.txt`, `.log`, `.md` |
| `hirs-znak.svg` | znak HiRS w nagłówku i jako ikona karty przeglądarki |
| `makieta-*.png`, `polmedi-group-logo-white.svg` | ilustracje |
| `hirs-smtp-pass.txt.przyklad` | wzór pliku z hasłem |

### Znak HiRS

`hirs-znak.svg` powtarza kształt ikony aplikacji z hirs-demo.polmedi.com — biały krzyż
na zaokrąglonym kwadracie — ale zamiast płaskiego błękitu `#2a85f9` ma markową
przejściówkę Polmedi `#2448c8 → #09afaf`. Kolory nie są próbkowane z rastra logo,
tylko wzięte ze stałych `NIEBIESKI`/`TURKUS` w generatorze prezentacji uniwersalnej,
gdzie zapisano je ze strony polmedi.com. Geometria (promień 16, ramię 80 × 25 na
kanwie 128) zdjęta z oryginalnej ikony, więc znak jest tym samym kształtem, nie
podobnym. Wektor, bo stoi w nagłówku i w ikonie karty jednocześnie.

**Ten sam plik jest wgrany jako ikona aplikacji HiRS** (Ustawienia → ikona aplikacji,
24.08.2026). Poprzednia wersja z płaskim błękitem leży w
[`../../mockup/HiRS-ikona-przed-przejsciowka.png`](../../mockup/HiRS-ikona-przed-przejsciowka.png)
— gdyby trzeba było wrócić, wystarczy wgrać ją tym samym ekranem. Ikona mieszka
w bazie, nie w obrazie aplikacji, więc zmiana nie wymagała wdrożenia i nie zniknie
przy kolejnym.

## Wdrożenie w pięciu krokach

1. Wgraj zawartość katalogu do katalogu publicznego (`public_html`, `www`).
2. **Utwórz plik z hasłem — najlepiej PIĘTRO WYŻEJ niż strony**, czyli obok
   `public_html`, a nie w środku:

   ```
   /home/klient/hirs-smtp-pass.txt        ← tak
   /home/klient/public_html/hirs-smtp-pass.txt   ← ostateczność
   ```

   W pliku ma być samo hasło, w jednej linii, bez cudzysłowów. Nadaj mu prawa `600`.
3. Sprawdź `konfiguracja.php` — zwłaszcza `host` i `port`. Domyślnie
   `polmedi.com:587` (STARTTLS). Sporo hostingów wymaga `mail.polmedi.com`
   albo portu `465`.
4. Wejdź na `demo.php`, wyślij próbne zgłoszenie i sprawdź skrzynkę.
5. Jeśli nie doszło — zajrzyj do dziennika błędów PHP (`error_log`). Zapisujemy tam
   dokładny powód, bo użytkownikowi go nie pokazujemy.

### Dlaczego hasło ma leżeć poza katalogiem publicznym

`.htaccess` blokuje pliki `.txt`, ale **działa tylko na Apache'u**. Po przeniesieniu
na nginx albo po zmianie konfiguracji hostingu blokada znika po cichu, a hasło staje
się dostępne pod `https://…/hirs-smtp-pass.txt`. Plik piętro wyżej jest nieosiągalny
przez przeglądarkę niezależnie od serwera. `konfiguracja.php` sprawdza obie lokalizacje,
zaczynając od bezpieczniejszej.

Hasło jest w `.gitignore` — do repozytorium nie trafi ani ono, ani dziennik zgłoszeń.

## Co robi formularz

Pola: imię i nazwisko, szpital/organizacja, e-mail (wszystkie obowiązkowe), telefon,
wiadomość oraz **obowiązkowy checkbox zgody** na przetwarzanie danych w celu
przedstawienia oferty. Pod formularzem stoi klauzula informacyjna RODO.

Zabezpieczenia:

- **niewidoczne pole-pułapka** — wypełnione oznacza robota; udajemy wtedy sukces
  i nic nie wysyłamy (komunikat „wykryto robota” tylko podpowiada, jak omijać),
- **czas wypełniania** — poniżej 3 sekund traktujemy jak automat,
- **blokada wstrzykiwania nagłówków** — znak nowego wiersza w polu jednowierszowym
  odrzuca zgłoszenie; bez tego dałoby się dopisać własne `Bcc`,
- **kopia w dzienniku** (`hirs-zgloszenia.log` piętro wyżej) — zgłoszenie nie ginie,
  nawet gdy poczta akurat nie działa.

Nadawcą wiadomości jest `hirs@polmedi.com`, a adres zainteresowanego trafia
w `Reply-To`. Odwrotnie się nie da: wiadomość „od” cudzej domeny odrzuci SPF.

## Sprawdzone przed oddaniem

Formularz przeszedł 15 prób na PHP 8.3 (`php -S` w kontenerze): pokazywanie pól,
odrzucenie bez zgody z zachowaniem wpisanych danych, zły adres e-mail, puste pola
obowiązkowe, wstrzyknięcie nagłówka przez nową linię, pułapka na roboty, zbyt szybkie
wysłanie, brak pliku z hasłem, strona podziękowania oraz nieudane połączenie SMTP
(czytelny komunikat zamiast białej strony, bez ujawniania szczegółów serwera).

Strona: brak poziomego paska przewijania przy 1280 px i 390 px, wszystkie kotwice
prowadzą do istniejących sekcji, wszystkie obrazy się wczytują.

## Do uzupełnienia przed publikacją

- **Klauzula RODO** w `demo.php` jest wzorcowa. Trzeba ją przejrzeć z osobą
  odpowiedzialną za ochronę danych i uzupełnić pełne dane administratora
  (adres siedziby, KRS, ewentualny inspektor ochrony danych).
- **Warunki handlowe** w sekcji „Warunki” przeniesione z prezentacji — sprawdź kwoty
  przed publikacją w internecie.
- Jeśli hosting ma certyfikat z niepasującą nazwą, połączenie SMTP zostanie odrzucone
  (`verify_peer` jest włączone celowo). Wtedy popraw `host` na nazwę z certyfikatu —
  nie wyłączaj weryfikacji.

## Podgląd lokalny

```bash
docker run --rm -p 8099:8099 -v "$PWD:/app" -w /app php:8.3-cli php -S 0.0.0.0:8099
```

Potem `http://localhost:8099/`. Sam `index.html` otwarty z dysku też się wyświetli,
ale formularz wymaga PHP.
