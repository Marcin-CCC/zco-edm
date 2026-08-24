<?php
/**
 * Podstrona „Zamów dostęp do demo”: formularz i jego obsługa w jednym pliku.
 *
 * Jeden plik, a nie formularz + osobny `wyslij.php`, bo przy błędzie trzeba pokazać
 * te same pola z tym, co użytkownik już wpisał. Przy dwóch plikach wymagałoby to
 * sesji albo przepisywania wartości przez adres — niepotrzebna komplikacja.
 *
 * Po udanej wysyłce przekierowujemy na ten sam adres z `?wyslano=1` (wzorzec
 * POST-Redirect-GET): odświeżenie strony nie wysyła zgłoszenia drugi raz.
 */

declare(strict_types=1);

$USTAWIENIA = require __DIR__ . '/konfiguracja.php';

$bledy = [];
$dane = ['osoba' => '', 'organizacja' => '', 'email' => '', 'telefon' => '', 'wiadomosc' => ''];
$wyslano = isset($_GET['wyslano']);

/** Odczyt hasła z pierwszego istniejącego pliku. */
function odczytaj_haslo(array $sciezki): ?string
{
    foreach ($sciezki as $sciezka) {
        if (is_readable($sciezka)) {
            $haslo = trim((string) file_get_contents($sciezka));
            if ($haslo !== '') {
                return $haslo;
            }
        }
    }
    return null;
}

function zapisz_w_dzienniku(string $plik, array $dane, string $status): void
{
    if ($plik === '') {
        return;
    }
    $wiersz = sprintf(
        "%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
        date('c'), $status, $dane['osoba'], $dane['organizacja'],
        $dane['email'], $dane['telefon'], str_replace(["\r", "\n", "\t"], ' ', $dane['wiadomosc'])
    );
    @file_put_contents($plik, $wiersz, FILE_APPEND | LOCK_EX);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    foreach ($dane as $klucz => $_) {
        $dane[$klucz] = trim((string) ($_POST[$klucz] ?? ''));
    }
    $zgoda = isset($_POST['zgoda']);

    // --- odsiew automatów -------------------------------------------------
    // Pole „firma” jest niewidoczne dla człowieka (zob. `.pulapka` w stylach).
    // Wypełnione = robot, który wpisuje wszystko, co znajdzie w formularzu.
    $pulapka = trim((string) ($_POST['firma'] ?? ''));
    $poczatek = (int) ($_POST['czas'] ?? 0);
    $zaSzybko = $poczatek > 0 && (time() - $poczatek) < (int) $USTAWIENIA['minimalny_czas'];
    if ($pulapka !== '' || $zaSzybko) {
        // Botowi pokazujemy to samo, co człowiekowi — komunikat „wykryto robota”
        // tylko podpowiada, jak omijać zabezpieczenie. Nic nie wysyłamy.
        header('Location: demo.php?wyslano=1');
        exit;
    }

    // --- sprawdzenie pól --------------------------------------------------
    if ($dane['osoba'] === '') {
        $bledy[] = 'Podaj imię i nazwisko.';
    }
    if ($dane['organizacja'] === '') {
        $bledy[] = 'Podaj nazwę szpitala lub organizacji.';
    }
    if ($dane['email'] === '' || !filter_var($dane['email'], FILTER_VALIDATE_EMAIL)) {
        $bledy[] = 'Podaj poprawny adres e-mail — na niego odpiszemy.';
    }
    if (mb_strlen($dane['wiadomosc']) > 4000) {
        $bledy[] = 'Wiadomość jest za długa (maksymalnie 4000 znaków).';
    }
    if (!$zgoda) {
        $bledy[] = 'Bez zgody na przetwarzanie danych nie możemy odpisać na zgłoszenie.';
    }
    // Znak nowej linii w polu jednowierszowym to próba dopisania własnych nagłówków
    // do wiadomości. Adresy i nazwy nigdy ich nie zawierają.
    foreach (['osoba', 'organizacja', 'email', 'telefon'] as $pole) {
        if (preg_match('/[\r\n]/', $dane[$pole])) {
            $bledy[] = 'Pola formularza nie mogą zawierać znaku nowego wiersza.';
            break;
        }
    }

    if (!$bledy) {
        require __DIR__ . '/smtp.php';
        $haslo = odczytaj_haslo($USTAWIENIA['pliki_z_haslem']);
        if ($haslo === null) {
            $bledy[] = 'Formularz nie jest jeszcze skonfigurowany po stronie serwera. '
                     . 'Napisz proszę wprost na hirs@polmedi.com.';
            zapisz_w_dzienniku($USTAWIENIA['dziennik'], $dane, 'BRAK-HASLA');
        } else {
            $tresc = "Zgłoszenie z formularza „Zamów dostęp do demo” (HiRS)\n"
                . str_repeat('-', 58) . "\n\n"
                . "Osoba:        {$dane['osoba']}\n"
                . "Organizacja:  {$dane['organizacja']}\n"
                . "E-mail:       {$dane['email']}\n"
                . "Telefon:      " . ($dane['telefon'] !== '' ? $dane['telefon'] : '—') . "\n\n"
                . "Wiadomość:\n" . ($dane['wiadomosc'] !== '' ? $dane['wiadomosc'] : '—') . "\n\n"
                . str_repeat('-', 58) . "\n"
                . "Zgoda na przetwarzanie danych w celu przesłania oferty: TAK\n"
                . 'Wysłano: ' . date('Y-m-d H:i:s') . "\n"
                . 'Adres IP: ' . ($_SERVER['REMOTE_ADDR'] ?? 'nieznany') . "\n";

            try {
                $smtp = new Smtp(
                    $USTAWIENIA['host'], $USTAWIENIA['port'],
                    $USTAWIENIA['uzytkownik'], $haslo);
                $smtp->wyslij(
                    $USTAWIENIA['nadawca'], $USTAWIENIA['nazwa_nadawcy'],
                    $USTAWIENIA['odbiorca'], $dane['email'],
                    'HiRS — zamówienie demo: ' . $dane['organizacja'], $tresc);
                zapisz_w_dzienniku($USTAWIENIA['dziennik'], $dane, 'OK');
                header('Location: demo.php?wyslano=1');
                exit;
            } catch (Throwable $e) {
                // Treść błędu zostaje w dzienniku serwera; użytkownikowi nie pokazujemy
                // nazwy hosta ani kodów SMTP — to informacja dla atakującego, nie dla niego.
                error_log('[HiRS] Wysyłka nieudana: ' . $e->getMessage());
                zapisz_w_dzienniku($USTAWIENIA['dziennik'], $dane, 'BLAD-WYSYLKI');
                $bledy[] = 'Nie udało się wysłać zgłoszenia. Zapisaliśmy je u nas i oddzwonimy, '
                         . 'ale jeśli sprawa jest pilna — napisz na hirs@polmedi.com.';
            }
        }
    }
}

function h(?string $t): string
{
    return htmlspecialchars((string) $t, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
?>
<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zamów dostęp do demo — HiRS</title>
<meta name="description" content="Zamów pokaz systemu HiRS na działającej instancji z dokumentami przykładowymi.">
<meta name="robots" content="noindex, follow">
<link rel="icon" href="hirs-znak.svg" type="image/svg+xml">
<link rel="stylesheet" href="styl.css">
</head>
<body>

<header class="gora">
  <div class="srodek">
    <a class="marka" href="./">
      <img class="znak" src="hirs-znak.svg" alt="" width="38" height="38">
      <span><b>HiRS</b><span>Hospital Information Retrieval System</span></span>
    </a>
  </div>
</header>

<main class="srodek formularz-strona">
  <a class="wroc" href="./">← Wróć na stronę główną</a>

<?php if ($wyslano): ?>

  <div class="komunikat ok">
    <strong>Dziękujemy — zgłoszenie do nas dotarło.</strong><br>
    Odezwiemy się w ciągu jednego dnia roboczego na podany adres e-mail.
    Jeśli sprawa jest pilna, zadzwoń: 501 674 303 (Piotr Piątek).
  </div>
  <h1 style="font-size:32px;color:var(--granat);margin-top:26px">Co dalej</h1>
  <ul class="punkty">
    <li>Umawiamy pokaz w terminie, który Wam pasuje — zdalnie albo u Was.</li>
    <li>Pokazujemy działającą instancję z dokumentami przykładowymi, na Waszych pytaniach.</li>
    <li>Jeśli zechcecie, kolejnym krokiem jest dwutygodniowe uruchomienie próbne
        na Waszych dokumentach — u Was, bez zobowiązania.</li>
  </ul>

<?php else: ?>

  <p class="nadtytul">Zamów dostęp do demo</p>
  <h1 style="font-size:clamp(28px,4vw,38px);color:var(--granat);line-height:1.15">
    Zobaczcie HiRS na własnych pytaniach</h1>
  <p class="wstep">Wypełnijcie formularz — odezwiemy się w ciągu jednego dnia roboczego
    i umówimy pokaz. Nie instalujemy przy tym niczego u Was.</p>

  <?php if ($bledy): ?>
    <div class="komunikat zle" role="alert">
      <strong>Zgłoszenie nie zostało wysłane:</strong>
      <ul>
        <?php foreach ($bledy as $blad): ?>
          <li><?= h($blad) ?></li>
        <?php endforeach; ?>
      </ul>
    </div>
  <?php endif; ?>

  <form class="zamowienie" method="post" action="demo.php" novalidate>
    <input type="hidden" name="czas" value="<?= time() ?>">
    <div class="pulapka" aria-hidden="true">
      <label for="firma">Nazwa firmy (nie wypełniaj)</label>
      <input type="text" id="firma" name="firma" tabindex="-1" autocomplete="off">
    </div>

    <div class="pole">
      <label for="osoba">Imię i nazwisko <span class="wymagane" aria-hidden="true">*</span></label>
      <input type="text" id="osoba" name="osoba" required autocomplete="name"
             value="<?= h($dane['osoba']) ?>">
    </div>

    <div class="pole">
      <label for="organizacja">Szpital lub organizacja <span class="wymagane" aria-hidden="true">*</span></label>
      <input type="text" id="organizacja" name="organizacja" required autocomplete="organization"
             value="<?= h($dane['organizacja']) ?>">
    </div>

    <div class="pole">
      <label for="email">Adres e-mail <span class="wymagane" aria-hidden="true">*</span>
        <span class="podpowiedz">Na ten adres odpiszemy.</span></label>
      <input type="email" id="email" name="email" required autocomplete="email"
             value="<?= h($dane['email']) ?>">
    </div>

    <div class="pole">
      <label for="telefon">Telefon
        <span class="podpowiedz">Nieobowiązkowo — przyspiesza umówienie terminu.</span></label>
      <input type="tel" id="telefon" name="telefon" autocomplete="tel"
             value="<?= h($dane['telefon']) ?>">
    </div>

    <div class="pole">
      <label for="wiadomosc">Wiadomość
        <span class="podpowiedz">Czego dotyczą pytania, które chcielibyście zadać systemowi?</span></label>
      <textarea id="wiadomosc" name="wiadomosc"><?= h($dane['wiadomosc']) ?></textarea>
    </div>

    <div class="zgoda">
      <input type="checkbox" id="zgoda" name="zgoda" required
             <?= ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['zgoda'])) ? 'checked' : '' ?>>
      <label for="zgoda">
        Wyrażam zgodę na przetwarzanie moich danych osobowych podanych w formularzu przez
        Polmedi Group sp. z o.o. z siedzibą w Poznaniu w celu przedstawienia oferty
        i kontaktu w sprawie systemu HiRS. <span class="wymagane" aria-hidden="true">*</span>
      </label>
    </div>

    <button class="przycisk" type="submit">Wyślij zgłoszenie</button>
  </form>

  <div class="nota-rodo">
    <p><b>Informacja o przetwarzaniu danych.</b> Administratorem danych podanych
      w formularzu jest Polmedi Group sp. z o.o. z siedzibą w Poznaniu. Dane przetwarzamy
      na podstawie Twojej zgody (art. 6 ust. 1 lit. a RODO) wyłącznie po to, żeby
      odpowiedzieć na zgłoszenie i przedstawić ofertę. Podanie danych jest dobrowolne,
      ale bez adresu e-mail nie mamy jak odpisać.</p>
    <p style="margin-top:10px">Dane przechowujemy do czasu zakończenia rozmów handlowych
      lub wycofania zgody — zgodę możesz wycofać w każdej chwili, pisząc na
      <a href="mailto:hirs@polmedi.com">hirs@polmedi.com</a>; nie wpływa to na zgodność
      z prawem przetwarzania sprzed wycofania. Masz prawo dostępu do swoich danych, ich
      sprostowania, usunięcia, ograniczenia przetwarzania, przenoszenia oraz wniesienia
      skargi do Prezesa Urzędu Ochrony Danych Osobowych. Danych nie przekazujemy poza
      Europejski Obszar Gospodarczy i nie podejmujemy na ich podstawie decyzji
      w sposób automatyczny.</p>
  </div>

<?php endif; ?>
</main>

<footer>
  <div class="srodek">
    <div>
      <strong style="color:#fff">Polmedi Group sp. z o.o.</strong> · Poznań ·
      <a href="https://polmedi.com">polmedi.com</a><br>
      <a href="mailto:hirs@polmedi.com">hirs@polmedi.com</a>
    </div>
    <img src="polmedi-group-logo-white.svg" alt="Polmedi Group">
  </div>
</footer>

</body>
</html>
