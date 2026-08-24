<?php
/**
 * Ustawienia formularza. Jedyny plik, który trzeba dotknąć po wgraniu na serwer.
 *
 * HASŁA TU NIE MA — leży w osobnym pliku tekstowym, żeby dało się je zmienić bez
 * ruszania kodu i żeby nie trafiło do repozytorium.
 */

return [
    // Dokąd idzie zgłoszenie.
    'odbiorca' => 'hirs@polmedi.com',

    // Konto, z którego wysyłamy. Adres nadawcy MUSI należeć do domeny uwierzytelnionej
    // na serwerze — inaczej SPF domeny odrzuci wiadomość albo wrzuci ją do spamu.
    // Dlatego nadawcą jest nasza skrzynka, a adres zainteresowanego idzie w `Reply-To`.
    'nadawca' => 'hirs@polmedi.com',
    'nazwa_nadawcy' => 'Formularz HiRS',

    'host' => 'polmedi.com',
    // 587 = STARTTLS (zalecane), 465 = szyfrowanie od pierwszego bajtu.
    // Jeśli hosting wymaga innego adresu (np. mail.polmedi.com), zmień „host” powyżej.
    'port' => 587,
    'uzytkownik' => 'hirs@polmedi.com',

    // Ścieżki sprawdzane po kolei; wygrywa pierwsza istniejąca. Wariant „katalog wyżej”
    // jest PIERWSZY celowo: plik poza katalogiem publikowanym przez serwer jest
    // nieosiągalny przez przeglądarkę nawet wtedy, gdy .htaccess przestanie działać
    // (przesiadka na nginx, zmiana konfiguracji hostingu).
    'pliki_z_haslem' => [
        __DIR__ . '/../hirs-smtp-pass.txt',
        __DIR__ . '/hirs-smtp-pass.txt',
    ],

    // Kopia zgłoszenia w pliku — ratunek, gdy poczta nie zadziała. Pusty napis wyłącza.
    // Ten plik również trzymamy poza katalogiem publicznym.
    'dziennik' => __DIR__ . '/../hirs-zgloszenia.log',

    // Najkrótszy czas wypełniania formularza uznany za ludzki (sekundy).
    'minimalny_czas' => 3,
];
