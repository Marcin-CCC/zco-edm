"""Generator instrukcji obsługi ZCO Document Management (wydanie administratora i użytkownika).

Obie instrukcje powstają z jednego zestawu sekcji — rozdziały wspólne dla obu ról są
zdefiniowane raz i użyte w obu dokumentach, żeby opis tego samego ekranu nie rozjechał
się między wydaniami. Wynik to samodzielne pliki HTML (zrzuty ekranu wbudowane jako
data URI), z których Edge w trybie headless drukuje PDF-y.

Uruchomienie:
    python generuj.py [katalog_ze_zrzutami]

Zrzuty ekranu robi skrypt shot.py (zob. README obok) — nazwy plików: aNN-*.png dla
wydania administratora, uNN-*.png dla wydania użytkownika.
"""
import base64
import html
import os
import subprocess
import sys
import tempfile
import time

WERSJA = "1.5.11"
DATA = "17 sierpnia 2026"
WYKONAWCA = "Polmedi Group sp. z o.o., Poznań"
KATALOG = os.path.dirname(os.path.abspath(__file__))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# --------------------------------------------------------------- wdrożenia
#
# Ta sama aplikacja stoi w dwóch miejscach: u klienta jako „ZCO DM" i jako demo
# uniwersalne „HiRS". Instrukcje różnią się WYŁĄCZNIE tym słownikiem i zrzutami
# ekranu — treść rozdziałów jest wspólna, bo obie instancje to ten sam obraz.
# Gdyby wydania pisać osobno, pierwsza poprawka trafiłaby tylko do jednego.
WDROZENIA = {
    "zco": {
        "nazwa": "ZCO DM",
        "pelna": "ZCO Document Management",
        "odbiorca": "Zachodniopomorskie Centrum Onkologii w Szczecinie",
        "wlasciciel": "Zachodniopomorskiego Centrum Onkologii",
        "plik": "ZCO-DM-instrukcja",
        # Zrzuty pochodzą z dokumentów klienta, nie z danych przykładowych.
        "zrodlo_zrzutow": "Zrzuty ekranu pochodzą z działającej instancji "
                          "i przedstawiają rzeczywiste dokumenty ZCO.",
        "demo": False,
    },
    "hirs": {
        "nazwa": "HiRS",
        "pelna": "Hospital Information Retrieval System",
        "odbiorca": "wersja demonstracyjna",
        "wlasciciel": "szpitala",
        "plik": "HiRS-instrukcja",
        "zrodlo_zrzutow": "Zrzuty ekranu pochodzą z instancji demonstracyjnej "
                          "i przedstawiają dokumenty przykładowe.",
        "demo": True,
    },
}

# Bieżące wdrożenie — ustawiane w main() z argumentu wywołania. Rozdziały czytają
# je przez W["..."], więc nie ma w treści ani jednej nazwy wpisanej na sztywno.
W = WDROZENIA["zco"]


# ---------------------------------------------------------------- bloki treści

def a(tekst):
    return ("p", tekst)


def n(tekst):
    return ("h3", tekst)


def lista(*punkty):
    return ("ul", punkty)


def kroki(*punkty):
    return ("ol", punkty)


def tabela(naglowki, wiersze):
    return ("table", (naglowki, wiersze))


def zrzut(plik, podpis):
    return ("fig", (plik, podpis))


def wskazowka(tekst):
    return ("tip", tekst)


def uwaga(tekst):
    return ("warn", tekst)


# ------------------------------------------------------- rozdziały wspólne

def r_o_aplikacji():
    return [
        a(f"{W['pelna']} (w skrócie <b>{W['nazwa']}</b>) to wewnętrzna baza dokumentów. "
          "Aplikacja robi dwie rzeczy naraz: przechowuje dokumenty w uporządkowanej strukturze "
          "folderów i pozwala <b>zadawać pytania o ich treść zwykłym językiem</b>, tak jak "
          "zapytalibyśmy kolegi, który te dokumenty zna."),
        a("Różnica wobec zwykłego dysku sieciowego jest zasadnicza. Na dysku trzeba wiedzieć, "
          "w którym pliku szukać. Tutaj wystarczy zapytać „jakie są zasady pracy zdalnej?”, a aplikacja "
          "sama znajdzie właściwe fragmenty dokumentów, ułoży z nich odpowiedź i pokaże, z których "
          "dokumentów pochodzi każde zdanie."),
        n("Dwie drogi do dokumentu"),
        a("Aplikacja odpowiada na dwa różne rodzaje pytań i ma na nie dwa osobne ekrany. "
          "<b>Chat z AI</b> odpowiada na pytania o <b>treść</b> — „od jakiego wieku dziecka "
          "przysługuje dofinansowanie?”. <b>Wyszukiwanie</b> odpowiada na pytania o <b>strukturę</b> — "
          "„pokaż wszystkie zarządzenia z 2023 roku”. Rozdzielenie jest celowe: dzięki niemu nie trzeba "
          "zgadywać, do którego pola wpisać pytanie."),
        n("Co się dzieje z dokumentem po wgraniu"),
        a("Każdy dokument przechodzi automatyczne przetwarzanie. Aplikacja odczytuje jego treść "
          "(także z tabel), dzieli ją na fragmenty, rozpoznaje rodzaj dokumentu — zarządzenie, procedura, "
          "wniosek — i wyciąga z niego pola opisowe, na przykład numer, datę czy osobę zatwierdzającą. "
          "Dopiero po tym dokument staje się widoczny dla wyszukiwania i dla czatu."),
        a("Przetwarzanie jednego dokumentu trwa zwykle od kilkunastu sekund do kilku minut — zależnie "
          "od jego długości i od tego, czy jest to plik tekstowy, czy skan wymagający rozpoznania pisma. "
          "Przez ten czas dokument ma status <i>W kolejce</i> lub <i>Przetwarzanie</i>."),
        n("Bezpieczeństwo danych"),
        a("Cała aplikacja wraz z modelem językowym działa na serwerze "
          f"{W['wlasciciel']}. <b>Treść dokumentów ani zadawane pytania nie opuszczają tego serwera</b> "
          "i nie są wysyłane do żadnej usługi zewnętrznej. Dostęp do dokumentów wynika z uprawnień "
          "nadanych roli, do której należy konto — użytkownik widzi wyłącznie te foldery, "
          "które mu udostępniono."),
        uwaga("Aplikacja jest narzędziem pomocniczym. Odpowiedź czatu zawsze wskazuje dokument źródłowy "
              "i to on pozostaje wiążący — przy decyzjach formalnych należy sięgnąć do wskazanego dokumentu."),
    ]

def r_logowanie(rola):
    bloki = [
        a("Aplikację otwieramy w przeglądarce internetowej pod adresem podanym przez administratora. "
          "Nad formularzem widnieje znak instancji — ikona i nazwa. Logujemy się <b>adresem e-mail</b> "
          "i hasłem otrzymanym od administratora; wielkość liter w adresie nie ma znaczenia."),
        zrzut("a00-logowanie.png" if rola == "admin" else "u00-logowanie.png",
              "Ekran logowania. Znak instancji nad formularzem jest ten sam, "
              "który widać potem na szczycie menu."),
        a("Po zalogowaniu ekran dzieli się na dwie części. Po lewej stronie znajduje się granatowe menu, "
          "po prawej — treść wybranej strony. W prawym górnym rogu widoczne są imię i nazwisko oraz "
          "<b>kółko z inicjałami</b>, które rozwija menu użytkownika. Na dole menu bocznego widnieje "
          "numer wersji aplikacji — będący odnośnikiem do historii zmian — oraz informacja o producencie."),
        n("Zwijanie menu"),
        a("Kliknięcie w znak instancji na szczycie menu <b>zwija je do samych ikon</b>, zostawiając "
          "więcej miejsca na treść. Ponowne kliknięcie rozwija menu z powrotem. Wybór jest zapamiętywany "
          "między sesjami, więc raz zwinięte menu pozostanie zwinięte także po ponownym zalogowaniu."),
        n("Menu pod inicjałami"),
        lista(
            "<b>Profil</b> — własne dane konta i zmiana hasła.",
            "<b>Instrukcja</b> — ten dokument, otwarty wprost w aplikacji; można go też pobrać jako PDF.",
            "<b>Wyloguj</b> — zakończenie pracy.",
        ),
        n("Pozycje menu bocznego"),
        lista(
            "<b>Dashboard</b> — ekran startowy z podsumowaniem liczbowym i wykresami aktywności.",
            "<b>Pliki</b> — eksplorator folderów i dokumentów.",
            "<b>Chat z AI</b> — pytania o treść dokumentów.",
            "<b>Wyszukiwanie</b> — wyszukiwarka po polach opisowych.",
        ),
    ]
    if rola == "admin":
        bloki += [
            a("Poniżej znajduje się kreska z podpisem <b>ADMINISTRACJA</b>, a pod nią część widoczna "
              "wyłącznie dla administratora: <b>Użytkownicy</b>, <b>Lista dostępów</b>, "
              "<b>Schematy dokumentów</b>, <b>Kolejka plików</b>, <b>Lista odpowiedzi</b> "
              "oraz <b>Ustawienia</b>. Te same pozycje pojawiają się dodatkowo jako pasek zakładek "
              "na górze każdego ekranu administracyjnego."),
        ]
    else:
        bloki.append(a("Jeżeli ktoś inny widzi w menu dodatkową część pod kreską <b>ADMINISTRACJA</b>, "
                       "oznacza to, że ma konto administratora. Zwykłe konto tej części aplikacji "
                       "nie widzi i nie ma do niej dostępu."))
    bloki += [
        a("Na dole menu jest jeszcze kafelek <b>Potrzebujesz pomocy?</b> z przyciskiem "
          "<b>Skontaktuj się</b> — prowadzi do formularza zgłoszenia do wsparcia technicznego "
          "(zob. osobny rozdział). Gdy menu nie mieści się na niskim ekranie, przewija się sama lista "
          "pozycji; kafelek pomocy i stopka pozostają na swoim miejscu."),
        wskazowka("Po okresie bezczynności aplikacja wylogowuje automatycznie — to zabezpieczenie "
                  "na wypadek pozostawienia otwartej sesji na wspólnym komputerze. Długość tego okresu "
                  "ustawia administrator; niezależnie od niej sesja ma twardy limit dwunastu godzin."),
    ]
    return bloki

def r_profil(rola):
    """Własne konto i pomoc — rozdział wspólny, różni się tylko wzmianką o rolach."""
    bloki = [
        a("Kółko z inicjałami w prawym górnym rogu rozwija menu z trzema pozycjami: "
          "<b>Profil</b>, <b>Instrukcja</b> i <b>Wyloguj</b>. Menu zamyka się klawiszem Escape "
          "albo kliknięciem obok."),
        *([zrzut("a18-menu-awatara.png", "Menu użytkownika rozwinięte spod kółka z inicjałami.")]
          if rola == "admin" else []),
        n("Strona Profil"),
        a("Strona <b>Profil</b> pokazuje dane konta: nazwę wyświetlaną, imię i nazwisko, adres e-mail, "
          "przypisaną rolę, status konta oraz datę ostatniego logowania."),
        zrzut("a16-profil.png" if rola == "admin" else "u05-profil.png",
              "Strona Profil — dane konta oraz osobna karta do zmiany hasła."),
        a("Przycisk <b>Edytuj dane</b> zamienia trzy pierwsze pozycje w pola formularza. Zapisujemy "
          "przyciskiem <b>Zapisz</b>, wycofujemy się przyciskiem <b>Anuluj</b>."),
        lista(
            "<b>Nazwa wyświetlana</b> — pokazuje się w powitaniu, w inicjałach i w zestawieniach "
            "administratora. Nie służy do logowania, więc można ją zmieniać dowolnie.",
            "<b>Imię i nazwisko</b> — pełna forma, używana na stronie Profil i w menu.",
            "<b>Adres e-mail</b> — <b>tym adresem logujemy się do aplikacji</b>. Po jego zmianie "
            "kolejne logowanie odbywa się już nowym adresem.",
        ),
        uwaga("Roli ani statusu konta nie zmienia się samodzielnie — robi to administrator. "
              "Gdyby wpisany adres e-mail albo nazwa były już zajęte przez inne konto, aplikacja "
              "powie o tym wprost i nie zapisze zmiany."),
        n("Zmiana hasła"),
        a("Hasło zmieniamy w osobnej karcie <b>Hasło</b>, przyciskiem <b>Zmień hasło</b>. Formularz prosi "
          "o hasło obecnie używane oraz o dwukrotne wpisanie nowego. Nowe hasło musi mieć co najmniej "
          "osiem znaków i różnić się od dotychczasowego."),
        a("Po udanej zmianie aplikacja wylogowuje i pokazuje ekran logowania — to celowe: od razu "
          "sprawdzamy, że nowe hasło działa."),
        n("Pomoc"),
        a("Pozycja <b>Instrukcja</b> otwiera stronę <b>Pomoc</b> z tym dokumentem wprost w aplikacji, bez szukania pliku na dysku. "
          "Na górze strony są dwa przyciski: <b>Otwórz w nowej karcie</b> oraz <b>Pobierz PDF</b>. "
          "Administrator widzi wydanie pełne, pozostałe konta — wydanie użytkownika, opisujące wyłącznie "
          "ekrany, do których mają dostęp."),
        zrzut("a17-pomoc.png" if rola == "admin" else "u06-pomoc.png",
              "Strona Pomoc — instrukcja obsługi wbudowana w aplikację."),
    ]
    return bloki


def r_dashboard(rola):
    bloki = [
        a("<b>Dashboard</b> to ekran startowy. Pokazuje stan bazy dokumentów w liczbach i wykresach, "
          "a wszystko na nim dotyczy <b>wybranego zakresu czasu</b> — listy rozwijanej w prawym górnym "
          "rogu, z opcjami 7, 30 i 90 dni. Jeden wybór obowiązuje cały ekran, więc kafelki i wykresy "
          "zawsze mówią o tym samym okresie."),
        zrzut("a01-pulpit.png" if rola == "admin" else "u01-pulpit.png",
              "Dashboard — kafelki podsumowania i wykresy aktywności."),
        n("Kafelki na górze"),
        a("Cztery kafelki podają liczbę kont, folderów i dokumentów oraz udział dokumentów "
          "przetworzonych. Pod liczbą bywa druga linijka z porównaniem do poprzedniego okresu, "
          "na przykład <i>↑ 12,6% wobec poprzednich 30 dni</i>."),
        wskazowka("Brak linijki z porównaniem nie oznacza usterki. Aplikacja nie pokazuje zmiany "
                  "procentowej, gdy poprzedni okres był zbyt ubogi, żeby procent cokolwiek znaczył — "
                  "wzrost „o 400%” z jednego dokumentu na pięć jest liczbą prawdziwą i bezużyteczną."),
        n("Wykresy"),
        a("Dwa wykresy pokazują dzienną aktywność: liczbę przetworzonych dokumentów i liczbę pytań "
          "zadanych czatowi. Najechanie kursorem pokazuje dokładną wartość z danego dnia."),
    ]
    if rola == "admin":
        bloki += [
            n("Ostatnio dodane dokumenty i aktywność użytkowników"),
            a("Dwa panele pod wykresami pokazują pięć ostatnio wgranych dokumentów oraz zestawienie "
              "aktywności kont w wybranym okresie — ile plików ktoś wgrał i ile zadał pytań. Konta "
              "bez żadnej aktywności nie zaśmiecają listy; ich liczba jest podana pod spodem."),
            n("Szybkie akcje, miejsce i stan serwera"),
            a("Dolny rząd to trzy panele. <b>Szybkie akcje</b> prowadzą wprost do najczęstszych "
              "czynności. <b>Miejsce w systemie</b> pokazuje zajętość dysku serwera — uwaga: całego "
              "dysku, dzielonego z pozostałymi usługami, dlatego pod spodem podana jest osobno "
              "wielkość samych dokumentów. <b>Status systemu</b> mówi, czy działają aplikacja, baza "
              "danych, parser dokumentów i magazyn plików."),
            zrzut("a19-panele.png", "Dolny rząd Dashboardu: szybkie akcje, zajętość dysku "
                                    "i stan poszczególnych usług."),
            wskazowka("W wierszu <b>Parser</b> widać, czy model językowy jest w tej chwili zajęty. "
                      "„Model bezczynny” oznacza, że nowe pytanie albo dokument zostaną obsłużone od razu; "
                      "gdy model coś liczy, odpowiedź czatu może chwilę poczekać."),
        ]
    else:
        bloki.append(a("Liczby na Dashboardzie dotyczą <b>tego, co wolno nam zobaczyć</b>. Dokumenty "
                       "i foldery liczone są w zakresie nadanych uprawnień, a wykres pytań pokazuje "
                       "wyłącznie pytania zadane z własnego konta. Dwie osoby o różnych uprawnieniach "
                       "zobaczą więc na tym ekranie różne liczby i jest to zachowanie prawidłowe."))
    return bloki

def r_pliki_przegladanie(rola):
    bloki = [
        a("Ekran <b>Pliki</b> to eksplorator dokumentów. Na górze widnieje ścieżka nawigacji "
          "zaczynająca się od <b>Katalogu głównego</b> — kliknięcie dowolnego jej elementu cofa "
          "do tego poziomu. Poniżej są dwie karty: <b>Foldery</b> i <b>Pliki</b>."),
        zrzut("a02-pliki.png" if rola == "admin" else "u02-pliki.png",
              "Eksplorator plików — foldery bieżącego poziomu i lista dokumentów."),
        n("Dwa widoki"),
        a("Zarówno foldery, jak i pliki można oglądać jako <b>listę</b> albo jako <b>kafelki</b> — "
          "przełącznik znajduje się w nagłówku każdej z kart, a wybór jest niezależny dla folderów "
          "i dla plików. Lista mieści więcej informacji w jednym rzucie oka, kafelki są wygodniejsze, "
          "gdy szukamy dokumentu „z pamięci wzrokowej”."),
        zrzut("a02b-kafelki.png" if rola == "admin" else "u02b-folder.png",
              "Widok kafelkowy — typ pliku niesie kolorowa plakietka z rozszerzeniem."),
        n("Kolumny listy"),
        a("Lista plików pokazuje typ pliku, nazwę, rozmiar, <b>kategorię</b> rozpoznaną przez aplikację "
          "oraz datę dodania. Kategoria to rodzaj dokumentu — zarządzenie, procedura, wniosek — "
          "i to ona najczęściej pomaga odnaleźć właściwy plik. Dokumenty, których aplikacja nie "
          "przypisała do żadnej kategorii, mają w tej kolumnie napis <i>nierozpoznana</i>."),
        n("Szukanie i stronicowanie"),
        a("Pole <b>Szukaj pliku</b> nad listą filtruje dokumenty po nazwie w obrębie bieżącego folderu. "
          "Pod listą widnieje liczba dokumentów oraz wybór, ile pozycji pokazywać na stronie "
          "(10, 25, 50 lub 100)."),
        uwaga("Aplikacja pobiera naraz najwyżej 200 dokumentów z folderu. Gdy folder zawiera ich więcej, "
              "pod listą pojawia się o tym czerwona adnotacja — wtedy trzeba zawęzić wyszukiwanie "
              "albo wejść do podfolderu. Lista nigdy nie ukrywa dokumentów po cichu."),
        n("Szczegóły dokumentu"),
        a("Kliknięcie wiersza otwiera okno ze szczegółami: typ pliku, rozmiar, status przetwarzania, "
          "datę dodania, folder, konto które wgrało dokument oraz rozpoznaną kategorię. Z tego okna "
          "można dokument <b>pobrać</b>, a pliki PDF również <b>podejrzeć</b> w nowej karcie."),
    ]
    if rola == "admin":
        bloki.append(zrzut("a07-szczegoly.png", "Okno szczegółów dokumentu z przyciskami pobrania "
                                                "i podglądu."))
    else:
        bloki.append(a("W katalogu głównym zwykłe konto nie widzi żadnych plików — dokumenty leżące "
                       "poza folderami są dostępne wyłącznie dla administratora. Widoczne są za to "
                       "foldery, które udostępniono naszej roli."))
    return bloki

def r_wgrywanie(rola):
    bloki = [
        a("Dokumenty dodajemy przyciskiem <b>Prześlij pliki</b> w prawym górnym rogu strony Pliki. "
          "Trafiają one do folderu, który jest w danej chwili otwarty — dlatego <b>najpierw wchodzimy "
          "do właściwego folderu, a dopiero potem wgrywamy</b>. Docelowy folder jest zawsze wypisany "
          "w oknie wysyłki."),
        zrzut("a03-wysylka.png" if rola == "admin" else "a03-wysylka.png",
              "Okno wysyłki: dozwolone formaty, limit rozmiaru i wskazanie folderu docelowego."),
        a("Można zaznaczyć wiele plików naraz. Aplikacja pokazuje wtedy postęp osobno dla każdego z nich, "
          "a na końcu podsumowanie: ile plików wgrano i ile zakończyło się błędem."),
        n("Dozwolone formaty"),
        a("Aplikacja przyjmuje pliki <b>PDF, DOCX, ODT i XLSX</b>, każdy o rozmiarze do 100 MB. Lista formatów "
          "jest widoczna w oknie wysyłki i pochodzi wprost z ustawień aplikacji — jeżeli administrator ją "
          "zmieni, okno pokaże nową listę, a systemowe okno wyboru pliku odfiltruje pozostałe rozszerzenia."),
        uwaga("Nazwa pliku ma znaczenie. Aplikacja używa jej jako podpowiedzi przy rozpoznawaniu rodzaju "
              "dokumentu, a także wyświetla ją w wynikach wyszukiwania i w odpowiedziach czatu. "
              "Nazwa w rodzaju „Zarządzenie nr 8-2023 praca zdalna.pdf” jest znacznie użyteczniejsza "
              "niż „skan_0001.pdf”."),
    ]
    if rola != "admin":
        bloki.append(a("Przycisk <b>Prześlij pliki</b> pojawia się tylko w folderach, do których mamy prawo "
                       "zapisu. W folderach udostępnionych wyłącznie do odczytu widzimy dokumenty i możemy "
                       "je pobierać, ale nie możemy nic dodać ani usunąć."))
    return bloki


def r_czat(rola):
    bloki = [
        a("Ekran <b>Chat z AI</b> to miejsce, w którym zadajemy pytania o treść dokumentów. "
          "Dzieli się na trzy części: listę wcześniejszych rozmów po lewej, okno rozmowy pośrodku "
          "i odsyłacz do wyszukiwarki po prawej."),
        a("Pytanie wpisujemy w pole na dole i zatwierdzamy klawiszem <b>Enter</b>; "
          "<b>Shift+Enter</b> przechodzi do nowej linii. Odpowiedź pojawia się stopniowo, "
          "słowo po słowie — można ją przerwać przyciskiem <b>Zatrzymaj</b>."),
        zrzut("a08-chat.png" if rola == "admin" else "u03-chat.png",
              "Odpowiedź czatu wraz z listą dokumentów, na których została oparta."),
        n("Skąd pochodzi odpowiedź"),
        a("Pod każdą odpowiedzią widnieje lista <b>dokumentów użytych w odpowiedzi</b>. Każda pozycja "
          "podaje numer odsyłacza, typ pliku, kategorię dokumentu, stronę i nazwę pliku; kliknięcie "
          "otwiera dokument źródłowy. Numery w plakietkach odpowiadają odsyłaczom w treści odpowiedzi, "
          "więc widać, które zdanie skąd pochodzi."),
        a("Poniżej bywa jeszcze informacja w rodzaju <i>Sprawdzono też 7 dokumentów, które nie zostały "
          "wykorzystane</i> wraz z przyciskiem rozwijającym ich listę. To dokumenty, które aplikacja "
          "przejrzała, szukając odpowiedzi, ale nie znalazła w nich niczego na temat — warto tam "
          "zajrzeć, gdy odpowiedź wydaje się niepełna."),
        n("Gdy w dokumentach nie ma odpowiedzi"),
        a("Aplikacja odpowiada <b>wyłącznie na podstawie wgranych dokumentów</b>. Jeżeli nie znajdzie "
          "informacji, napisze o tym wprost, zamiast zmyślać. Odpowiedź „nie znaleziono w dokumentach "
          "informacji na ten temat” jest zatem informacją o zbiorze dokumentów, a nie usterką."),
        n("Pytania o listę dokumentów"),
        a("Pytanie w rodzaju „pokaż wszystkie zarządzenia z 2023 roku” aplikacja rozpoznaje jako prośbę "
          "o <b>wypis</b>, nie o odpowiedź z treści. Odpowiada wtedy zdaniem „Znalazłem N dokumentów”, "
          "listą tych dokumentów i przyciskiem <b>Pobierz tę listę w pliku XLSX</b>."),
        n("Rozmowy"),
        a("Każda rozmowa zapisuje się na liście po lewej stronie i można do niej wrócić. Przycisk "
          "<b>Nowy chat</b> zaczyna rozmowę od czysta. Ma to znaczenie: w obrębie jednej rozmowy "
          "aplikacja bierze pod uwagę wcześniejsze pytania, więc <b>przy zmianie tematu lepiej "
          "zacząć nową</b>."),
        wskazowka("Pytania „o to samo innymi słowami” bywają skuteczne. Jeżeli pierwsza odpowiedź "
                  "jest ogólna, warto dopytać o szczegół — aplikacja szuka wtedy w obrębie dokumentów "
                  "wskazanych w poprzedniej odpowiedzi."),
    ]
    if rola == "admin":
        bloki.append(a("Pod odpowiedzią pojawia się prośba o ocenę. Oceny trafiają na ekran "
                       "<b>Lista odpowiedzi</b> w części administracyjnej i służą do poprawiania "
                       "jakości działania — warto zachęcić użytkowników, żeby z niej korzystali."))
    return bloki

def r_wyszukiwarka(rola):
    return [
        a("<b>Wyszukiwanie</b> to osobny ekran w menu. Odpowiada na pytania o <b>strukturę</b> zbioru: "
          "„wszystkie zarządzenia z 2023 roku”, „wnioski podpisane przez konkretną osobę”. Czat "
          "odpowiada na pytania o treść — te dwie drogi celowo nie są wymieszane."),
        n("Zapytaj po polsku"),
        a("Najprościej wpisać pytanie zwykłym językiem w pole na górze. Kursor stoi w nim od razu "
          "po wejściu na ekran. Aplikacja rozpoznaje z pytania rodzaj dokumentu i warunki, "
          "<b>wypełnia nimi formularz poniżej</b> i od razu pokazuje wyniki. Rozpoznany filtr można "
          "potem poprawić ręcznie i wyszukać ponownie."),
        zrzut("a09-wyszukiwarka.png" if rola == "admin" else "u04-wyszukiwarka.png",
              "Wyszukiwarka po polach: pytanie po polsku, rozpoznany filtr i lista wyników."),
        n("Formularz"),
        a("Formularz składa się z rodzaju dokumentu i dowolnej liczby warunków. Warunek to pole "
          "opisowe, operator (<i>zawiera</i>, <i>równe</i>, <i>od</i>, <i>do</i>, <i>po</i>, "
          "<i>przed</i>) i wartość. Lista dostępnych pól zależy od wybranego rodzaju dokumentu — "
          "pochodzi wprost ze schematów dokumentów."),
        n("Wyniki"),
        a("Wyniki wyglądają tak samo jak lista dokumentów pod odpowiedzią czatu: numer, typ pliku, "
          "kategoria, nazwa dokumentu i nazwa pliku. Kliknięcie otwiera dokument. Nad listą jest "
          "przycisk <b>Pobierz tę listę w pliku XLSX</b> — arkusz zawiera komplet pól opisowych, "
          "z kolumnami w kolejności ustalonej w schemacie dokumentu."),
        wskazowka("Wyszukiwarka działa na <b>polach opisowych</b>, a nie na treści. Dokument, "
                  "z którego aplikacja nie zdołała wyciągnąć numeru ani daty, nie pojawi się "
                  "w wynikach filtrowanych po tych polach — znajdzie się natomiast przez czat."),
    ]

def r_dobre_praktyki(rola):
    bloki = [
        lista(
            "Nadawać dokumentom nazwy mówiące, czym są — ułatwia to rozpoznanie rodzaju i późniejsze szukanie.",
            "Wgrywać dokumenty do folderu tematycznego, a nie do katalogu głównego.",
            "Sprawdzać status po wgraniu: dopiero <i>Przetworzono</i> oznacza, że dokument odpowiada na pytania.",
            "Przy zmianie tematu zaczynać nowy chat, żeby poprzednie pytania nie wpływały na odpowiedź.",
            "Przy sprawach formalnych otwierać dokument źródłowy wskazany pod odpowiedzią.",
        ),
    ]
    if rola == "admin":
        bloki.append(lista(
            "Nadawać uprawnienia rolom na możliwie wysokim folderze — podfoldery dziedziczą je automatycznie.",
            "Po większej partii dokumentów przejrzeć Kolejkę plików i poprawić błędnie rozpoznane rodzaje.",
            "Konta osób, które odeszły, dezaktywować zamiast usuwać — zachowuje to historię operacji.",
        ))
    return bloki


def r_faq(rola):
    wspolne = [
        ["Wgrałem dokument, ale czat go nie zna.",
         "Sprawdzić status na liście plików. Dopóki nie jest <i>Przetworzono</i>, dokument nie bierze udziału "
         "w wyszukiwaniu. Przy długich dokumentach przetwarzanie trwa kilka minut."],
        ["Czat odpowiada, że nie znalazł informacji.",
         "Najczęściej pytanie dotyczy dokumentu, którego nie ma w bazie, albo dokument nie jest jeszcze "
         "przetworzony. Warto też zadać pytanie inaczej — pełnym zdaniem."],
        ["Nie widzę folderu, o którym mówi współpracownik.",
         "Foldery są udostępniane rolom. Jeżeli brakuje dostępu, należy poprosić administratora o nadanie "
         "uprawnienia do tego folderu."],
        ["Aplikacja wylogowała mnie sama.",
         "Po okresie bezczynności ustalonym przez administratora sesja wygasa. Wystarczy zalogować się ponownie."],
        ["Nie mogę wgrać pliku — okno wyboru go nie pokazuje.",
         "Aplikacja przyjmuje formaty PDF, DOCX, ODT i XLSX. Pliki w innych formatach trzeba najpierw zapisać "
         "w jednym z nich."],
        ["Nie mogę się zalogować nazwą użytkownika.",
         "Do logowania służy wyłącznie adres e-mail przypisany do konta. Nazwa użytkownika jest tylko "
         "nazwą wyświetlaną."],
        ["Zapomniałem hasła.",
         "Nowe hasło ustawia administrator w module Użytkownicy. Po zalogowaniu warto zmienić je na własne "
         "na stronie Profil."],
        ["Gdzie znajdę tę instrukcję w aplikacji?",
         "Pod kółkiem z inicjałami w prawym górnym rogu, pozycja Pomoc. Stamtąd można ją też pobrać jako PDF."],
    ]
    admin = [
        ["Dokument został rozpoznany jako niewłaściwy rodzaj.",
         "W Kolejce plików można ręcznie wskazać właściwy rodzaj; aplikacja od razu wyciągnie pola na nowo."],
        ["Nowy pracownik nie widzi żadnych dokumentów.",
         "Konto ma rolę, ale rola nie ma jeszcze uprawnień do folderów. Uprawnienia nadaje się w widoku Pliki, "
         "ikoną klucza przy folderze."],
        ["Chcę dodać nowy rodzaj dokumentu z własnymi polami.",
         "Służy do tego strona Schematy dokumentów w Administracji."],
    ]
    return [
        a("Poniżej najczęstsze sytuacje zgłaszane przy pierwszym kontakcie z aplikacją."),
        tabela(["Sytuacja", "Co zrobić"], wspolne + (admin if rola == "admin" else [])),
    ]


def r_slowniczek():
    return [
        tabela(["Pojęcie", "Znaczenie"], [
            ["Chat z AI", "Ekran, na którym zadajemy pytania o treść dokumentów."],
            ["Wyszukiwanie", "Ekran, na którym filtrujemy dokumenty po polach opisowych."],
            ["Chat / czat", "Rozmowa z aplikacją prowadzona zwykłym językiem."],
            ["Fragment (chunk)", "Kawałek dokumentu, na jakie aplikacja dzieli treść, żeby precyzyjnie "
                                 "wskazywać źródło odpowiedzi."],
            ["Parsowanie", "Odczytanie treści dokumentu i przygotowanie jej do wyszukiwania."],
            ["Pole opisowe", "Informacja opisująca dokument — numer, data, osoba zatwierdzająca."],
            ["Rodzaj dokumentu", "Kategoria rozpoznana automatycznie: zarządzenie, procedura, wniosek i inne."],
            ["Rola", "Grupa uprawnień przypisana kontu — to rolom, a nie osobom, udostępnia się foldery."],
            ["Źródło", "Dokument i strona, z których pochodzi dany fragment odpowiedzi."],
        ]),
    ]


# ------------------------------------------------- rozdziały tylko dla admina

def r_porzadkowanie():
    return [
        a("Porządkowanie zbioru dokumentów to zadanie administratora. Wszystkie opisane niżej "
          "czynności wykonuje się na ekranie <b>Pliki</b>."),
        n("Nowy folder"),
        a("Przycisk <b>Nowy folder</b> tworzy podfolder w miejscu, w którym aktualnie jesteśmy. "
          "Okno pokazuje, jakie uprawnienia nowy folder odziedziczy po folderze nadrzędnym — "
          "to widok informacyjny, uprawnienia zmienia się później ikoną kłódki."),
        n("Zmiana nazwy folderu"),
        a("Ikona ołówka na kafelku folderu (widoczna po najechaniu) zmienia jego nazwę. Zmiana obejmuje "
          "ścieżkę tego folderu oraz wszystkich jego podfolderów; pliki i uprawnienia pozostają "
          "przypisane bez zmian."),
        zrzut("a05-zmiana-nazwy.png", "Zmiana nazwy folderu — operacja dostępna wyłącznie "
                                      "dla administratora."),
        n("Przenoszenie dokumentów"),
        a("Pojedynczy dokument przenosi się ikoną folderu ze strzałką w jego wierszu. Lista folderów "
          "docelowych jest ułożona alfabetycznie i zawiera wyłącznie te, w których mamy prawo zapisu."),
        zrzut("a06-przenoszenie.png", "Przenoszenie dokumentu do innego folderu."),
        n("Operacje na wielu dokumentach naraz"),
        a("Zaznaczenie dokumentów polami wyboru po lewej stronie odsłania przycisk "
          "<b>Wykonaj akcję na zaznaczonych</b> z dwiema możliwościami: <b>Przenieś do folderu</b> "
          "oraz <b>Nadaj nazwy zgodne z kategorią</b> (opisane w rozdziale o rozpoznawaniu dokumentów). "
          "Pole wyboru w nagłówku zaznacza dokumenty <b>z bieżącej strony</b>, a nie całą listę."),
        n("Usuwanie"),
        a("Ikona kosza usuwa dokument wraz z jego fragmentami w bazie wiedzy — po usunięciu przestaje "
          "on pojawiać się w odpowiedziach czatu. Usunięcie folderu przenosi jego dokumenty "
          "do katalogu głównego, więc nic nie ginie razem z folderem."),
        uwaga("Usunięcia dokumentu nie da się cofnąć z poziomu aplikacji. Przed usunięciem większej "
              "partii warto pobrać zestawienie dokumentów do arkusza — służy do tego przycisk "
              "<b>Pobierz tę listę w pliku XLSX</b> na ekranie Wyszukiwanie."),
    ]

def r_uprawnienia():
    return [
        a("Dostęp do dokumentów wynika z <b>roli</b>, do której należy konto, i z uprawnień nadanych "
          "tej roli na folderach. Uprawnień nie nadaje się pojedynczym osobom — dzięki temu przy "
          "zmianie stanowiska wystarczy zmienić rolę konta, zamiast poprawiać dziesiątki folderów."),
        n("Dwa poziomy dostępu"),
        lista(
            "<b>Odczyt</b> — rola widzi dokumenty w folderze, może je otwierać i pobierać, "
            "a ich treść bierze udział w odpowiedziach czatu.",
            "<b>Zapis</b> — dodatkowo można wgrywać nowe dokumenty, przenosić je i usuwać.",
        ),
        n("Dziedziczenie"),
        a("Uprawnienie nadane folderowi obejmuje <b>także jego podfoldery</b>. W oknie uprawnień "
          "pozycje odziedziczone są opisane jako <i>(dziedziczone z nadrzędnego)</i> i nie da się ich "
          "tam usunąć — zmienia się je na folderze nadrzędnym. Na podfolderze można dostęp wyłącznie "
          "<b>rozszerzyć</b>, na przykład podnieść Odczyt do Zapisu."),
        zrzut("a04-uprawnienia.png", "Okno uprawnień folderu — role, poziomy dostępu "
                                     "i uprawnienia dziedziczone."),
        n("Zarządzanie rolami"),
        a("Role definiuje się na ekranie <b>Lista dostępów</b> przyciskiem <b>Dodaj rolę</b>. Rolę można "
          "też przemianować i usunąć. Warto znać trzy zasady, które aplikacja egzekwuje:"),
        lista(
            "<b>Zmiana nazwy zmienia tylko etykietę.</b> Wewnętrzny kod roli pozostaje ten sam, więc "
            "nadane wcześniej uprawnienia i przypisania kont działają dalej bez zmian.",
            "<b>Ról systemowych nie da się usunąć</b> — Administrator i Gość są częścią działania "
            "aplikacji.",
            "<b>Usunięcie roli, do której należą konta, wymaga wskazania roli zastępczej.</b> "
            "Aplikacja przeniesie do niej te konta, żeby żadne nie zostało bez przypisania.",
        ),
        zrzut("a11b-rola.png", "Dodawanie nowej roli — kod roli powstaje z nazwy."),
        n("Podgląd całości"),
        a("Ekran <b>Lista dostępów</b> pokazuje zestawienie wszystkich ról i folderów w jednym miejscu, "
          "więc widać na nim od razu, kto co widzi. Kliknięcie folderu prowadzi wprost do niego "
          "w eksploratorze."),
        zrzut("a11-lista-dostepow.png", "Lista dostępów — zestawienie uprawnień wszystkich ról."),
        uwaga("Administrator widzi wszystkie foldery niezależnie od nadanych uprawnień. Dokumenty "
              "leżące w katalogu głównym, poza jakimkolwiek folderem, są widoczne <b>wyłącznie</b> "
              "dla administratora — dlatego dokument wgrany „do korzenia” nie pojawi się nikomu innemu "
              "ani w wyszukiwaniu, ani w czacie."),
    ]

def r_administracja():
    return [
        a("Część administracyjna leży w menu pod kreską <b>ADMINISTRACJA</b> i jest widoczna wyłącznie "
          "dla kont administratora. Te same pozycje powtarza pasek zakładek na górze każdego z tych "
          "ekranów."),
        n("Użytkownicy"),
        a("Zakładanie kont, zmiana roli, dezaktywacja i resetowanie hasła. Konto loguje się "
          "<b>adresem e-mail</b>; nazwa wyświetlana służy tylko do pokazywania w interfejsie "
          "i może się powtarzać."),
        zrzut("a10-uzytkownicy.png", "Zarządzanie kontami użytkowników."),
        n("Lista dostępów"),
        a("Zestawienie uprawnień wszystkich ról oraz zarządzanie samymi rolami — opisane "
          "w rozdziale o uprawnieniach."),
        n("Schematy dokumentów"),
        a("Rodzaje dokumentów wraz z polami opisowymi, kryteriami rozpoznawania i wzorcem nazwy pliku. "
          "To ekran, który najmocniej wpływa na jakość działania wyszukiwarki — opisany w rozdziale "
          "o rozpoznawaniu dokumentów."),
        zrzut("a12-schematy.png", "Schematy dokumentów — rodzaje dokumentów wraz z polami opisowymi."),
        n("Kolejka plików"),
        a("Podgląd przetwarzania: co czeka, co jest w trakcie, co się nie powiodło. Widać tu rozpoznany "
          "rodzaj dokumentu i wyciągnięte pola, więc jest to pierwsze miejsce, do którego warto zajrzeć, "
          "gdy dokument nie pojawia się w wynikach."),
        zrzut("a13-kolejka.png", "Kolejka plików — statusy, rozpoznane rodzaje i pola dokumentów."),
        n("Lista odpowiedzi"),
        a("Oceny wystawione odpowiedziom czatu wraz z pytaniem, odpowiedzią i wskazanymi dokumentami. "
          "Służy do wychwytywania pytań, na które aplikacja odpowiada źle — każda taka pozycja "
          "jest wskazówką, którego dokumentu brakuje albo który schemat wymaga poprawki."),
        n("Ustawienia"),
        a("Ekran dzieli się na trzy części."),
        lista(
            "<b>Identyfikacja aplikacji</b> — nazwa instancji, kolor napisu i ikona. Ikona musi być "
            "kwadratowym plikiem PNG albo SVG (zalecane minimum 128×128 px); pojawia się na szczycie "
            "menu i na ekranie logowania. Podgląd obok pokazuje dokładnie to, co zobaczy użytkownik.",
            "<b>Integracje i sesja</b> — adresy webhooków przetwarzania i czatu, lista dozwolonych "
            "rozszerzeń plików oraz czas do automatycznego wylogowania.",
            "<b>Poczta wychodząca</b> — dane serwera SMTP i adres wsparcia. Bez nich formularz "
            "„Skontaktuj się” odpowie wprost, że wysyłka nie jest skonfigurowana.",
        ),
        zrzut("a14-ustawienia.png", "Ustawienia aplikacji — identyfikacja instancji."),
        uwaga("Lista dozwolonych rozszerzeń musi odpowiadać temu, co obsługuje przepływ przetwarzania. "
              "Rozszerzenie dopisane tutaj, a nieobsługiwane tam, sprawi, że plik zostanie przyjęty, "
              "ale nigdy nie zostanie przetworzony."),
        n("Historia zmian"),
        a("Numer wersji na dole menu bocznego prowadzi do listy zmian w kolejnych wydaniach aplikacji. "
          "Ta strona jest dostępna dla wszystkich zalogowanych."),
        zrzut("a15-historia-zmian.png", "Historia zmian aplikacji."),
    ]

def r_rozpoznawanie():
    return [
        a("Po wgraniu dokumentu aplikacja próbuje ustalić, <b>czym on jest</b>, i wyciągnąć z niego "
          "pola opisowe. Robi to na podstawie <b>schematów dokumentów</b> — definicji rodzajów "
          "dokumentów, które administrator ustala na osobnym ekranie."),
        n("Z czego składa się schemat"),
        lista(
            "<b>Nazwa i identyfikator</b> rodzaju dokumentu, na przykład „Zarządzenie”.",
            "<b>Kryteria klasyfikacji</b> — wskazówki po polsku, po czym poznać ten rodzaj dokumentu.",
            "<b>Pola nagłówkowe</b> — co wyciągnąć z treści: numer, data, tytuł, osoba podpisująca. "
            "Kolejność pól wyznacza kolejność kolumn w eksporcie do arkusza.",
            "<b>Wzorzec nazwy pliku</b> — opcjonalny, opisany niżej.",
        ),
        n("Typy pól"),
        a("Każde pole ma typ: <b>Tekst</b>, <b>Data</b>, <b>Liczba</b>, <b>Kwota</b> albo "
          "<b>Lista wartości</b>. Typ nie jest ozdobą — decyduje o tym, co da się z polem zrobić. "
          "Daty pozwalają filtrować po zakresach, a kwoty trafiają do arkusza jako liczby z groszami, "
          "więc kolumna się sumuje (także wtedy, gdy w dokumencie zapisano ją jako „1 234,56 zł”)."),
        n("Nazwy plików z rozpoznanych pól"),
        a("Każdy rodzaj dokumentu może mieć <b>wzorzec nazwy pliku</b>, na przykład "
          "<i>{typ}-nr-{numer_dokumentu}-{data}</i>. Aplikacja proponuje wtedy nazwy zgodne z treścią "
          "dokumentu zamiast „skan_0001.pdf”. Wzorzec pusty oznacza, że dla tej kategorii nazw "
          "nie proponujemy."),
        a("Nazwy nadaje się partiami: na ekranie <b>Pliki</b> zaznaczamy dokumenty i wybieramy "
          "<b>Wykonaj akcję na zaznaczonych → Nadaj nazwy zgodne z kategorią</b>. Okno pokazuje "
          "najpierw zestawienie <i>stara nazwa → nowa</i>; każdą pozycję można poprawić ręcznie albo "
          "odznaczyć. <b>Nic nie dzieje się bez tego podglądu.</b>"),
        zrzut("a20-nazwy.png", "Nadawanie nazw zgodnych z kategorią — podgląd przed zatwierdzeniem."),
        a("Dotychczasowa nazwa jest zapamiętywana i widoczna w szczegółach dokumentu, więc zmianę "
          "da się odtworzyć, a dokument pozostaje rozpoznawalny dla osoby, która pamięta go "
          "pod starą nazwą."),
        n("Gdy rozpoznanie zawiedzie"),
        a("Dokument, którego aplikacja nie przypisała do żadnego rodzaju, ma kategorię "
          "<i>nierozpoznana</i>. Nadal jest przeszukiwalny przez czat — nie znajdzie się natomiast "
          "w wyszukiwarce filtrującej po polach. Najczęstsze przyczyny to słabej jakości skan "
          "albo brak schematu opisującego ten rodzaj dokumentu."),
        wskazowka("Kolejka plików pokazuje, jakie pola udało się wyciągnąć z każdego dokumentu. "
                  "Jeżeli pole jest puste dla wielu dokumentów tego samego rodzaju, zwykle warto "
                  "poprawić kryteria klasyfikacji albo nazwę pola w schemacie."),
    ]

def r_kontakt(rola):
    return [
        a("Kafelek <b>Potrzebujesz pomocy?</b> na dole menu bocznego prowadzi do formularza zgłoszenia "
          "do wsparcia technicznego. Wystarczy opisać sprawę i wysłać — nadawca i instancja "
          "dołączane są automatycznie, a odpowiedź trafi na adres e-mail przypisany do konta."),
        zrzut("a21-kontakt.png" if rola == "admin" else "u07-kontakt.png",
              "Formularz zgłoszenia do wsparcia technicznego."),
        a("Zgłoszenie idzie <b>pocztą, a nie przez mechanizm przetwarzania dokumentów</b>. Jest to "
          "celowe: awaria przetwarzania nie może odcinać drogi zgłoszenia problemu, bo właśnie wtedy "
          "zgłoszenia są najbardziej potrzebne."),
        wskazowka("Warto napisać, <b>co się robiło</b> i <b>czego się spodziewało</b>, a nie tylko "
                  "„nie działa”. Nazwa ekranu, treść pytania zadanego czatowi albo nazwa dokumentu "
                  "skracają diagnozę o kilka wymian wiadomości."),
    ]


def r_ograniczenia():
    wstep = ("Aplikacja jest rozwijana etapami. Poniższe ograniczenia są znane i zaplanowane "
             "do usunięcia — warto je znać, żeby nie brać ich za usterki.")
    if W["demo"]:
        wstep = ("Ta instancja jest wersją demonstracyjną, działającą na dokumentach przykładowych. "
                 "Poza tym jest to dokładnie ta sama aplikacja co wdrożenia klienckie. "
                 "Poniższe ograniczenia są znane i zaplanowane do usunięcia.")
    return [
        a(wstep),
        lista(
            "Aplikacja odpowiada wyłącznie na podstawie dokumentów wgranych do bazy — nie zna przepisów "
            "ani wiedzy spoza nich.",
            "Odpowiedź czatu jest streszczeniem fragmentów dokumentów. Przy sprawach formalnych "
            "obowiązuje dokument źródłowy wskazany pod odpowiedzią.",
            "Rozpoznawanie rodzaju dokumentu i pól opisowych działa dobrze na dokumentach o typowej "
            "budowie; dokumenty nietypowe mogą wymagać ręcznej korekty rodzaju.",
            "Podgląd dokumentu otwiera plik PDF w nowej karcie przeglądarki. Przeglądarka wbudowana "
            "w aplikację — otwierająca dokument od razu na wskazanej stronie — jest w planach.",
            "Powiązania między dokumentami (na przykład zarządzenie i jego załączniki) nie są jeszcze "
            "prezentowane w interfejsie.",
            "Wyszukiwarka po polach opisowych nie przeszukuje treści dokumentów — od tego jest czat.",
        ),
        a("Każda zmiana jest opisywana w <b>Historii zmian</b> dostępnej z poziomu aplikacji, "
          "spod numeru wersji na dole menu."),
    ]

# ---------------------------------------------------------------- dokumenty

def dokument_admina():
    return [
        (f"Czym jest {W['pelna']}", r_o_aplikacji()),
        ("Logowanie i układ ekranu", r_logowanie("admin")),
        ("Dashboard", r_dashboard("admin")),
        ("Twoje konto i instrukcja", r_profil("admin")),
        ("Przeglądanie dokumentów", r_pliki_przegladanie("admin")),
        ("Dodawanie dokumentów", r_wgrywanie("admin")),
        ("Porządkowanie: foldery, przenoszenie, usuwanie", r_porzadkowanie()),
        ("Uprawnienia i role", r_uprawnienia()),
        ("Chat z AI — pytania o treść dokumentów", r_czat("admin")),
        ("Wyszukiwanie po polach opisowych", r_wyszukiwarka("admin")),
        ("Administracja", r_administracja()),
        ("Jak aplikacja rozpoznaje dokumenty", r_rozpoznawanie()),
        ("Zgłoszenie do wsparcia technicznego", r_kontakt("admin")),
        ("Dobre praktyki", r_dobre_praktyki("admin")),
        ("Ograniczenia i plany rozwoju", r_ograniczenia()),
        ("Najczęstsze pytania", r_faq("admin")),
        ("Słowniczek", r_slowniczek()),
    ]


def dokument_uzytkownika():
    return [
        (f"Czym jest {W['pelna']}", r_o_aplikacji()),
        ("Logowanie i układ ekranu", r_logowanie("user")),
        ("Dashboard", r_dashboard("user")),
        ("Twoje konto i instrukcja", r_profil("user")),
        ("Przeglądanie dokumentów", r_pliki_przegladanie("user")),
        ("Dodawanie dokumentów", r_wgrywanie("user")),
        ("Chat z AI — pytania o treść dokumentów", r_czat("user")),
        ("Wyszukiwanie po polach opisowych", r_wyszukiwarka("user")),
        ("Zgłoszenie do wsparcia technicznego", r_kontakt("user")),
        ("Dobre praktyki", r_dobre_praktyki("user")),
        ("Najczęstsze pytania", r_faq("user")),
        ("Słowniczek", r_slowniczek()),
    ]


# ---------------------------------------------------------------- renderowanie

STYL = """
:root { --tekst:#1e293b; --szary:#64748b; --linia:#e2e8f0; --akcent:#2563eb; --tlo:#f8fafc; }
* { box-sizing:border-box; }
body { margin:0; font-family:"Segoe UI",Arial,sans-serif; color:var(--tekst);
       font-size:11.5pt; line-height:1.6; }
.strona { max-width:180mm; margin:0 auto; padding:10mm; }
h1 { font-size:26pt; line-height:1.2; margin:0 0 6mm; }
h2 { font-size:16pt; margin:0 0 4mm; padding-bottom:2mm; border-bottom:2px solid var(--akcent); }
h3 { font-size:12.5pt; margin:7mm 0 2mm; color:#0f172a; }
p { margin:0 0 3mm; text-align:justify; }
ul,ol { margin:0 0 4mm; padding-left:6mm; }
li { margin-bottom:1.5mm; }
table { width:100%; border-collapse:collapse; margin:0 0 5mm; font-size:10.5pt; }
th { background:var(--tlo); text-align:left; font-weight:600; }
th,td { border:1px solid var(--linia); padding:2mm 2.5mm; vertical-align:top; }
figure { margin:4mm 0 6mm; break-inside:avoid; }
figure img { width:100%; border:1px solid var(--linia); border-radius:3px; display:block; }
figcaption { font-size:9.5pt; color:var(--szary); margin-top:1.5mm; font-style:italic; }
.tip,.warn { padding:3mm 4mm; margin:0 0 4mm; border-radius:3px; font-size:10.5pt; break-inside:avoid; }
.tip { background:#eff6ff; border-left:3px solid var(--akcent); }
.warn { background:#fff7ed; border-left:3px solid #ea580c; }
.tip b.etykieta,.warn b.etykieta { display:block; font-size:9pt; letter-spacing:.06em;
       text-transform:uppercase; margin-bottom:1mm; }
.tip b.etykieta { color:var(--akcent); } .warn b.etykieta { color:#c2410c; }
.oklada { display:flex; flex-direction:column; justify-content:center; min-height:245mm; }
.oklada .kreska { width:28mm; height:4px; background:var(--akcent); margin-bottom:8mm; }
.oklada .wydanie { font-size:15pt; color:var(--akcent); font-weight:600; margin-bottom:14mm; }
.oklada dl { display:grid; grid-template-columns:38mm 1fr; gap:2.5mm 4mm; font-size:11pt; margin:0; }
.oklada dt { color:var(--szary); } .oklada dd { margin:0; }
.oklada .stopka { margin-top:auto; padding-top:10mm; border-top:1px solid var(--linia);
       font-size:10pt; color:var(--szary); }
.spis { break-after:page; }
.spis ol { list-style:none; padding:0; counter-reset:r; }
.spis li { counter-increment:r; padding:1.5mm 0; border-bottom:1px dotted var(--linia); }
.spis li::before { content:counter(r) ". "; color:var(--akcent); font-weight:600; }
.spis a { color:inherit; text-decoration:none; }
.do-gory { display:none; }
section { break-before:page; }
.naglowek-sekcji { font-size:9pt; color:var(--szary); letter-spacing:.08em;
       text-transform:uppercase; margin-bottom:2mm; }
@page { size:A4; margin:14mm 12mm; }
@media print { .strona { max-width:none; padding:0; } }
/* Na EKRANIE (podgląd w aplikacji, strona Pomoc) treść wypełnia dostępną szerokość.
   Sztywna kolumna 180 mm jest miarą kartki A4 — w oknie przeglądarki dawała wąski,
   drobny słupek tekstu i zrzuty ekranu wielkości znaczka pocztowego. Wydruk zostaje
   bez zmian, bo reguły druku są wyżej i w @media print. */
@media screen {
  body { font-size:13pt; }
  .strona { max-width:none; padding:8mm 12mm 14mm; }
  h1 { font-size:30pt; } h2 { font-size:19pt; } h3 { font-size:15pt; }
  table { font-size:12pt; } .tip,.warn { font-size:12pt; }
  figcaption { font-size:11pt; }
  p { max-width:170ch; }            /* sam tekst nie rozjeżdża się w nieczytelnie długie wiersze */
  section { padding-top:6mm; }
  .oklada { min-height:auto; padding-bottom:10mm; }
  .spis a { color:var(--akcent); }
  .spis li:hover { background:var(--tlo); }
  .do-gory { display:inline-block; margin-top:6mm; font-size:11pt; color:var(--szary);
             text-decoration:none; }
  .do-gory:hover { color:var(--akcent); }
  section { scroll-margin-top:4mm; }
}
"""


def obraz_data_uri(katalog_zrzutow, plik):
    """Zrzut wbudowany w HTML jako data URI. Brak pliku NIE przerywa generowania —
    instrukcja powstaje wtedy bez tej ilustracji, z ostrzeżeniem na konsoli. Pozwala to
    złożyć wydanie zanim powstanie zrzut ekranu, który sam tę instrukcję pokazuje."""
    sciezka = os.path.join(katalog_zrzutow, plik)
    if not os.path.exists(sciezka):
        print(f"  UWAGA: brak zrzutu {plik} — pomijam ilustrację")
        return None
    with open(sciezka, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def render_blok(blok, katalog_zrzutow):
    rodzaj, dane = blok
    if rodzaj == "p":
        return f"<p>{dane}</p>"
    if rodzaj == "h3":
        return f"<h3>{dane}</h3>"
    if rodzaj == "ul":
        return "<ul>" + "".join(f"<li>{x}</li>" for x in dane) + "</ul>"
    if rodzaj == "ol":
        return "<ol>" + "".join(f"<li>{x}</li>" for x in dane) + "</ol>"
    if rodzaj == "table":
        naglowki, wiersze = dane
        gl = "".join(f"<th>{h}</th>" for h in naglowki)
        tr = "".join("<tr>" + "".join(f"<td>{k}</td>" for k in w) + "</tr>" for w in wiersze)
        return f"<table><thead><tr>{gl}</tr></thead><tbody>{tr}</tbody></table>"
    if rodzaj == "fig":
        plik, podpis = dane
        src = obraz_data_uri(katalog_zrzutow, plik)
        if not src:
            return ""
        return (f'<figure><img src="{src}" alt="{html.escape(podpis)}">'
                f"<figcaption>{podpis}</figcaption></figure>")
    if rodzaj == "tip":
        return f'<div class="tip"><b class="etykieta">Wskazówka</b>{dane}</div>'
    if rodzaj == "warn":
        return f'<div class="warn"><b class="etykieta">Uwaga</b>{dane}</div>'
    raise ValueError(rodzaj)


def render(tytul_wydania, sekcje, katalog_zrzutow):
    # Kotwice: numer rozdziału zamiast slugu z tytułu — odnośnik przeżyje poprawkę
    # tytułu, a w PDF-ie Edge zamienia je na wewnętrzne przejścia do stron.
    spis = "".join(
        f'<li><a href="#rozdzial-{numer}">{html.escape(t)}</a></li>'
        for numer, (t, _) in enumerate(sekcje, start=1)
    )
    tresc = []
    for numer, (tytul, bloki) in enumerate(sekcje, start=1):
        ciało = "".join(render_blok(b, katalog_zrzutow) for b in bloki)
        tresc.append(
            f'<section id="rozdzial-{numer}">'
            f'<div class="naglowek-sekcji">Rozdział {numer}</div>'
            f'<h2>{html.escape(tytul)}</h2>{ciało}'
            f'<a class="do-gory" href="#spis-tresci">↑ Spis treści</a>'
            f"</section>"
        )
    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<title>{html.escape(W["pelna"])} — {html.escape(tytul_wydania)}</title>
<style>{STYL}</style></head><body><div class="strona">
<div class="oklada">
  <div class="kreska"></div>
  <h1>{html.escape(W["pelna"])}</h1>
  <div class="wydanie">Instrukcja obsługi — {html.escape(tytul_wydania)}</div>
  <dl>
    <dt>Odbiorca</dt><dd>{W["odbiorca"]}</dd>
    <dt>Wykonawca</dt><dd>{WYKONAWCA}</dd>
    <dt>Wersja aplikacji</dt><dd>{WERSJA}</dd>
    <dt>Data wydania</dt><dd>{DATA}</dd>
  </dl>
  <div class="stopka">Dokument wewnętrzny. {W["zrodlo_zrzutow"]}</div>
</div>
<section class="spis" id="spis-tresci"><h2>Spis treści</h2><ol>{spis}</ol></section>
{''.join(tresc)}
</div></body></html>"""


def do_pdf(html_path, pdf_path, limit_sekund=240):
    """Wydrukuj HTML do PDF-a przy pomocy Edge w trybie headless.

    Dwie pułapki, obie kosztowały czas przy pierwszym uruchomieniu:
    * poprawna nazwa flagi to --print-to-pdf-no-header (wariant --no-pdf-header-footer
      Edge po cichu ignoruje),
    * proces Edge kończy się kodem 0 ZANIM dopisze plik, więc na PDF-a trzeba
      poczekać i upewnić się, że jego rozmiar przestał rosnąć.
    """
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    profil = tempfile.mkdtemp(prefix="edge-pdf-")
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--print-to-pdf-no-header",
                    f"--user-data-dir={profil}", f"--print-to-pdf={pdf_path}",
                    "file:///" + html_path.replace("\\", "/")],
                   check=True, timeout=limit_sekund,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    poprzedni, stabilny_od = -1, 0.0
    czekano = 0.0
    while czekano < limit_sekund:
        time.sleep(1.0)
        czekano += 1.0
        if not os.path.exists(pdf_path):
            continue
        rozmiar = os.path.getsize(pdf_path)
        if rozmiar > 0 and rozmiar == poprzedni:
            stabilny_od += 1.0
            if stabilny_od >= 2.0:
                return
        else:
            stabilny_od = 0.0
        poprzedni = rozmiar
    raise RuntimeError(f"Edge nie ukonczyl pliku {pdf_path} w {limit_sekund} s")


def main():
    """python generuj.py <zco|hirs> [katalog_ze_zrzutami]

    Bez argumentu buduje oba wdrożenia po kolei — tak najczęściej się tego używa,
    bo instrukcje mają wychodzić parami i z tej samej wersji aplikacji.
    """
    global W
    warianty = [sys.argv[1]] if len(sys.argv) > 1 else list(WDROZENIA)
    for wariant in warianty:
        if wariant not in WDROZENIA:
            raise SystemExit(f"Nieznane wdrożenie: {wariant}. Dostępne: {', '.join(WDROZENIA)}")
        W = WDROZENIA[wariant]
        katalog_zrzutow = (sys.argv[2] if len(sys.argv) > 2
                           else os.path.join(KATALOG, "zrzuty", wariant))
        print(f"— {W['nazwa']} (zrzuty: {katalog_zrzutow})")
        zbuduj(katalog_zrzutow)


def zbuduj(katalog_zrzutow):
    wydania = [
        ("wydanie dla administratora", dokument_admina(), W["plik"] + "-administratora"),
        ("wydanie dla użytkownika", dokument_uzytkownika(), W["plik"] + "-uzytkownika"),
    ]
    for tytul, sekcje, nazwa in wydania:
        html_path = os.path.join(KATALOG, nazwa + ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render(tytul, sekcje, katalog_zrzutow))
        do_pdf(html_path, os.path.join(KATALOG, nazwa + ".pdf"))
        print(f"{nazwa}: {len(sekcje)} rozdziałów, "
              f"{os.path.getsize(html_path)//1024} KB HTML, "
              f"{os.path.getsize(os.path.join(KATALOG, nazwa + '.pdf'))//1024} KB PDF")


if __name__ == "__main__":
    main()
