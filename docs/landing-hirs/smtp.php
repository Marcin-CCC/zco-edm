<?php
/**
 * Minimalny klient SMTP — tyle, ile trzeba do wysłania jednej wiadomości tekstowej.
 *
 * Dlaczego własny, a nie PHPMailer: na hostingu współdzielonym nie ma pewności, czy
 * jest Composer, a wgrywanie biblioteki z zależnościami dla jednego formularza to
 * więcej kodu do pilnowania niż sto linii poniżej. Wymagania: `openssl` i
 * `stream_socket_client` — obecne w każdym sensownym PHP 7.4+.
 *
 * Dlaczego nie `mail()`: funkcja systemowa nie uwierzytelnia się na serwerze poczty,
 * więc wiadomość z formularza szłaby jako „nikt z nikąd” i lądowała w spamie albo
 * była odrzucana przez SPF domeny.
 */

class BladSmtp extends Exception {}

class Smtp
{
    private $polaczenie;
    private $host;
    private $port;
    private $uzytkownik;
    private $haslo;
    private $limit;

    public function __construct($host, $port, $uzytkownik, $haslo, $limit = 20)
    {
        $this->host = $host;
        $this->port = (int) $port;
        $this->uzytkownik = $uzytkownik;
        $this->haslo = $haslo;
        $this->limit = $limit;
    }

    /**
     * Wysyła jedną wiadomość. Rzuca `BladSmtp` z opisem etapu, na którym się wywróciło —
     * bez tego diagnoza sprowadzałaby się do „nie działa”.
     */
    public function wyslij($odNadawcy, $nazwaNadawcy, $doOdbiorcy, $odpowiedzDo, $temat, $tresc)
    {
        // Port 465 = szyfrowanie od pierwszego bajtu; 587 = jawnie, potem STARTTLS.
        $adres = ($this->port === 465 ? 'ssl://' : 'tcp://') . $this->host . ':' . $this->port;
        $kontekst = stream_context_create(['ssl' => [
            'verify_peer' => true,
            'verify_peer_name' => true,
            'SNI_enabled' => true,
        ]]);
        $blad = $kod = null;
        $this->polaczenie = @stream_socket_client(
            $adres, $kod, $blad, $this->limit, STREAM_CLIENT_CONNECT, $kontekst);
        if (!$this->polaczenie) {
            throw new BladSmtp("Nie można połączyć się z {$this->host}:{$this->port} ($blad)");
        }
        stream_set_timeout($this->polaczenie, $this->limit);

        try {
            $this->czytaj(220);
            $this->rozmowa();
            if ($this->port !== 465) {
                $this->polecenie('STARTTLS', 220);
                $ok = @stream_socket_enable_crypto(
                    $this->polaczenie, true, STREAM_CRYPTO_METHOD_TLS_CLIENT);
                if (!$ok) {
                    throw new BladSmtp('Nie udało się włączyć szyfrowania (STARTTLS)');
                }
                $this->rozmowa();   // po STARTTLS przedstawiamy się jeszcze raz — tak każe RFC
            }
            $this->uwierzytelnij();

            $this->polecenie('MAIL FROM:<' . $odNadawcy . '>', 250);
            $this->polecenie('RCPT TO:<' . $doOdbiorcy . '>', 250);
            $this->polecenie('DATA', 354);
            $this->pisz($this->zbudujWiadomosc(
                $odNadawcy, $nazwaNadawcy, $doOdbiorcy, $odpowiedzDo, $temat, $tresc));
            $this->pisz('.');
            $this->czytaj(250);
            $this->polecenie('QUIT', 221);
        } finally {
            if (is_resource($this->polaczenie)) {
                fclose($this->polaczenie);
            }
        }
        return true;
    }

    /** EHLO, a gdy serwer go nie zna — HELO. */
    private function rozmowa()
    {
        $nazwa = $this->nazwaKlienta();
        try {
            $this->polecenie('EHLO ' . $nazwa, 250);
        } catch (BladSmtp $e) {
            $this->polecenie('HELO ' . $nazwa, 250);
        }
    }

    /**
     * Nazwa, którą się przedstawiamy. Adres IP musi iść w nawiasach kwadratowych,
     * bo część serwerów odrzuca gołe cyfry jako niepoprawną nazwę domeny.
     */
    private function nazwaKlienta()
    {
        $nazwa = isset($_SERVER['SERVER_NAME']) ? $_SERVER['SERVER_NAME'] : 'localhost';
        if (filter_var($nazwa, FILTER_VALIDATE_IP)) {
            return '[' . $nazwa . ']';
        }
        return preg_match('/^[A-Za-z0-9.\-]+$/', $nazwa) ? $nazwa : 'localhost';
    }

    private function uwierzytelnij()
    {
        // AUTH LOGIN: serwer prosi kolejno o nazwę i hasło, każde w base64.
        $this->polecenie('AUTH LOGIN', 334);
        $this->polecenie(base64_encode($this->uzytkownik), 334);
        $this->polecenie(base64_encode($this->haslo), 235);
    }

    private function zbudujWiadomosc($od, $nazwaOd, $do, $odpowiedzDo, $temat, $tresc)
    {
        $naglowki = [
            'Date: ' . date('r'),
            'From: ' . $this->naglowekZNazwa($nazwaOd, $od),
            'To: <' . $do . '>',
            'Subject: ' . $this->zakoduj($temat),
            'MIME-Version: 1.0',
            'Content-Type: text/plain; charset=UTF-8',
            'Content-Transfer-Encoding: 8bit',
            'X-Mailer: HiRS landing',
        ];
        if ($odpowiedzDo) {
            // Dzięki temu „Odpowiedz” w kliencie poczty pisze do zainteresowanego,
            // a nie do skrzynki, z której poszło zgłoszenie.
            $naglowki[] = 'Reply-To: <' . $odpowiedzDo . '>';
        }
        $ciało = str_replace(["\r\n", "\r"], "\n", $tresc);
        $ciało = str_replace("\n", "\r\n", $ciało);
        // Kropka na początku wiersza kończy transmisję — trzeba ją podwoić (RFC 5321).
        $ciało = preg_replace('/^\./m', '..', $ciało);
        return implode("\r\n", $naglowki) . "\r\n\r\n" . $ciało;
    }

    private function naglowekZNazwa($nazwa, $adres)
    {
        return $nazwa ? $this->zakoduj($nazwa) . ' <' . $adres . '>' : '<' . $adres . '>';
    }

    /** Polskie znaki w temacie i nazwie nadawcy muszą iść zakodowane (RFC 2047). */
    private function zakoduj($tekst)
    {
        if (preg_match('/^[\x20-\x7E]*$/', $tekst)) {
            return $tekst;
        }
        return '=?UTF-8?B?' . base64_encode($tekst) . '?=';
    }

    private function polecenie($tresc, $oczekiwany)
    {
        $this->pisz($tresc);
        return $this->czytaj($oczekiwany, $tresc);
    }

    private function pisz($tresc)
    {
        if (fwrite($this->polaczenie, $tresc . "\r\n") === false) {
            throw new BladSmtp('Zerwane połączenie przy wysyłaniu polecenia');
        }
    }

    private function czytaj($oczekiwany, $poPoleceniu = '')
    {
        $odpowiedz = '';
        while (($linia = fgets($this->polaczenie, 515)) !== false) {
            $odpowiedz .= $linia;
            // Wieloliniowa odpowiedź ma myślnik po kodzie: „250-”. Spacja = ostatnia linia.
            if (strlen($linia) >= 4 && $linia[3] === ' ') {
                break;
            }
        }
        $kod = (int) substr($odpowiedz, 0, 3);
        if ($kod !== $oczekiwany) {
            $gdzie = $poPoleceniu ? ' po „' . $this->bezHasla($poPoleceniu) . '”' : '';
            throw new BladSmtp("Serwer odpowiedział $kod" . $gdzie . ': ' . trim($odpowiedz));
        }
        return $odpowiedz;
    }

    /** Hasło idzie w base64 — nie wolno mu trafić do logu razem z komunikatem błędu. */
    private function bezHasla($polecenie)
    {
        if (strpos($polecenie, 'AUTH') === 0 || !preg_match('/[^A-Za-z0-9+\/=]/', $polecenie)) {
            return '***';
        }
        return $polecenie;
    }
}
