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

WERSJA = "1.0.1"
DATA = "30 lipca 2026"
ODBIORCA = "Zachodniopomorskie Centrum Onkologii w Szczecinie"
WYKONAWCA = "Polmedi Group sp. z o.o., Poznań"
KATALOG = os.path.dirname(os.path.abspath(__file__))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


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
        a("ZCO Document Management (w skrócie <b>ZCO DM</b>) to wewnętrzna baza dokumentów "
          "Zachodniopomorskiego Centrum Onkologii. Aplikacja robi dwie rzeczy naraz: przechowuje "
          "dokumenty w uporządkowanej strukturze folderów i pozwala <b>zadawać pytania o ich treść "
          "zwykłym językiem</b>, tak jak zapytalibyśmy kolegi, który te dokumenty zna."),
        a("Różnica wobec zwykłego dysku sieciowego jest zasadnicza. Na dysku trzeba wiedzieć, "
          "w którym pliku szukać. Tutaj wystarczy zapytać „jakie są zasady pracy zdalnej?”, a aplikacja "
          "sama znajdzie właściwe fragmenty dokumentów, ułoży z nich odpowiedź i pokaże, z których "
          "dokumentów i z których stron pochodzi każde zdanie."),
        n("Co się dzieje z dokumentem po wgraniu"),
        a("Każdy dokument przechodzi automatyczne przetwarzanie. Aplikacja odczytuje jego treść "
          "(także z tabel), dzieli ją na fragmenty, rozpoznaje rodzaj dokumentu — zarządzenie, procedura, "
          "wniosek — i wyciąga z niego pola opisowe, na przykład numer, datę czy osobę zatwierdzającą. "
          "Dopiero po tym dokument staje się widoczny dla wyszukiwania i dla czatu."),
        a("Przetwarzanie jednego dokumentu trwa zwykle od kilkunastu sekund do kilku minut — zależnie "
          "od jego długości i od tego, czy jest to plik tekstowy, czy skan wymagający rozpoznania pisma. "
          "Przez ten czas dokument ma status <i>W kolejce</i> lub <i>Przetwarzanie</i>."),
        n("Bezpieczeństwo danych"),
        a("Cała aplikacja wraz z modelem językowym działa na serwerze w siedzibie ZCO. "
          "<b>Treść dokumentów ani zadawane pytania nie opuszczają tego serwera</b> i nie są wysyłane "
          "do żadnej usługi zewnętrznej. Dostęp do dokumentów wynika z uprawnień nadanych roli, "
          "do której należy konto — użytkownik widzi wyłącznie te foldery, które mu udostępniono."),
        uwaga("Aplikacja jest narzędziem pomocniczym. Odpowiedź czatu zawsze wskazuje dokument źródłowy "
              "i to on pozostaje wiążący — przy decyzjach formalnych należy sięgnąć do wskazanego dokumentu."),
    ]


def r_logowanie(rola):
    bloki = [
        a("Aplikację otwieramy w przeglądarce internetowej pod adresem podanym przez administratora. "
          "Logujemy się <b>adresem e-mail</b> i hasłem otrzymanym od administratora. Wielkość liter "
          "w adresie nie ma znaczenia."),
        a("Po zalogowaniu ekran dzieli się na dwie części. Po lewej stronie znajduje się granatowe menu, "
          "po prawej — treść wybranej strony. W prawym górnym rogu widoczne jest powitanie oraz "
          "<b>kółko z inicjałami</b>, które rozwija menu użytkownika. Na samym dole menu bocznego widnieje "
          "numer wersji aplikacji — będący odnośnikiem do historii zmian — oraz informacja o producencie."),
        n("Menu pod inicjałami"),
        lista(
            "<b>Profil</b> — własne dane konta i zmiana hasła.",
            "<b>Pomoc</b> — ta instrukcja, otwarta wprost w aplikacji; można ją też pobrać jako PDF.",
            "<b>Wyloguj</b> — zakończenie pracy.",
        ),
        n("Pozycje menu"),
    ]
    if rola == "admin":
        bloki.append(lista(
            "<b>Dashboard</b> — ekran startowy z podsumowaniem liczbowym i wykresami aktywności.",
            "<b>Pliki</b> — eksplorator folderów i dokumentów: wgrywanie, pobieranie, porządkowanie.",
            "<b>Baza wiedzy</b> — czat z dokumentami oraz wyszukiwarka po polach opisowych.",
            "<b>Administracja</b> — konta użytkowników, uprawnienia, rodzaje dokumentów, kolejka "
            "przetwarzania i ustawienia aplikacji. Ta pozycja jest widoczna wyłącznie dla administratora.",
        ))
    else:
        bloki.append(lista(
            "<b>Dashboard</b> — ekran startowy z podsumowaniem liczbowym i wykresami aktywności.",
            "<b>Pliki</b> — przeglądanie folderów i dokumentów, do których mamy dostęp.",
            "<b>Baza wiedzy</b> — czat z dokumentami oraz wyszukiwarka po polach opisowych.",
        ))
        bloki.append(a("Jeżeli ktoś inny widzi w menu dodatkową pozycję <b>Administracja</b>, oznacza to, "
                       "że ma konto administratora. Zwykłe konto tej części aplikacji nie widzi i nie ma "
                       "do niej dostępu."))
    bloki += [
        wskazowka("Po piętnastu minutach bezczynności aplikacja wylogowuje automatycznie. To zabezpieczenie "
                  "na wypadek pozostawienia otwartej sesji na wspólnym komputerze."),
    ]
    return bloki


def r_profil(rola):
    """Własne konto i pomoc — rozdział wspólny, różni się tylko wzmianką o rolach."""
    bloki = [
        a("Kółko z inicjałami w prawym górnym rogu rozwija menu z trzema pozycjami: "
          "<b>Profil</b>, <b>Pomoc</b> i <b>Wyloguj</b>. Menu zamyka się klawiszem Escape "
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
        a("Pozycja <b>Pomoc</b> otwiera tę instrukcję wprost w aplikacji, bez szukania pliku na dysku. "
          "Na górze strony są dwa przyciski: <b>Otwórz w nowej karcie</b> oraz <b>Pobierz PDF</b>. "
          "Administrator widzi wydanie pełne, pozostałe konta — wydanie użytkownika, opisujące wyłącznie "
          "ekrany, do których mają dostęp."),
        zrzut("a17-pomoc.png" if rola == "admin" else "u06-pomoc.png",
              "Strona Pomoc — instrukcja obsługi wbudowana w aplikację."),
    ]
    return bloki


def r_dashboard(rola):
    if rola == "admin":
        return [
            a("Dashboard to ekran startowy. U góry znajdują się cztery kafelki z podsumowaniem: liczba kont "
              "użytkowników, liczba dokumentów, liczba folderów oraz liczba dokumentów przetworzonych. "
              "Kafelek <b>Użytkownicy</b> prowadzi wprost do zarządzania kontami."),
            a("Poniżej widnieją dwa wykresy słupkowe obejmujące ostatnie trzydzieści dni: "
              "<b>Statystyki parsowania</b> pokazują, ile dokumentów zostało przetworzonych każdego dnia, "
              "a <b>Statystyki zapytań w chacie</b> — ile pytań zadano bazie wiedzy. Nad każdym wykresem "
              "widnieje suma z całego okresu, a po najechaniu kursorem na słupek pojawia się dokładna liczba "
              "wraz z datą."),
            a("Administrator widzi dane całej aplikacji, co jest zaznaczone opisem „wszyscy użytkownicy” "
              "przy każdym wykresie."),
            zrzut("a01-pulpit.png", "Dashboard administratora — kafelki podsumowania i wykresy aktywności z ostatnich 30 dni."),
            a("Pod wykresami widnieje sekcja <b>Aktywność wg użytkowników</b> — dwa wykresy poziome "
              "pokazujące, kto wysłał najwięcej plików do przetworzenia i kto zadał najwięcej pytań "
              "w ciągu ostatnich trzydziestu dni. Sekcję widzi wyłącznie administrator."),
            a("Danych własnego konta szukamy na stronie <b>Profil</b>, pod kółkiem z inicjałami "
              "w prawym górnym rogu."),
        ]
    return [
        a("Dashboard to ekran startowy. U góry znajdują się trzy kafelki: liczba dokumentów, liczba folderów "
          "oraz liczba dokumentów przetworzonych. <b>Wszystkie liczby dotyczą wyłącznie tego, do czego mamy "
          "dostęp</b> — jeżeli udostępniono nam dwa foldery, kafelki pokazują zawartość tych dwóch folderów, "
          "a nie całej aplikacji."),
        a("Poniżej widnieją dwa wykresy słupkowe z ostatnich trzydziestu dni. <b>Statystyki parsowania</b> "
          "pokazują, ile dostępnych dla nas dokumentów przetworzono każdego dnia — także tych wgranych przez "
          "współpracowników, jeśli trafiły do naszych folderów. <b>Statystyki zapytań w chacie</b> zliczają "
          "wyłącznie nasze własne pytania; cudze pozostają prywatne."),
        a("Opis nad każdym wykresem mówi wprost, czego dotyczy: „dostępne dla Ciebie” oraz „Twoje zapytania”."),
        zrzut("u01-pulpit.png", "Dashboard zwykłego użytkownika — liczby i wykresy w zakresie nadanych uprawnień."),
        a("Dane własnego konta znajdziemy na stronie <b>Profil</b>, pod kółkiem z inicjałami "
          "w prawym górnym rogu ekranu."),
    ]


def r_pliki_przegladanie(rola):
    bloki = [
        a("Strona <b>Pliki</b> działa jak eksplorator na komputerze. U góry widnieje ścieżka nawigacji "
          "zaczynająca się od <b>Root</b> — to katalog główny. Poniżej znajdują się kafelki folderów, "
          "a pod nimi lista dokumentów z bieżącego folderu."),
        a("Kliknięcie kafelka wchodzi do folderu, kliknięcie elementu ścieżki u góry cofa do wybranego poziomu. "
          "Listę dokumentów można przełączyć między widokiem <b>Lista</b> a <b>Kafelki</b>, a pole "
          "<i>Szukaj pliku…</i> filtruje dokumenty po nazwie."),
        a("Foldery i dokumenty ułożone są alfabetycznie, z uwzględnieniem polskich znaków — nazwy "
          "zaczynające się od ą, ć czy ł trafiają tam, gdzie powinny, a nie na koniec listy."),
    ]
    if rola == "admin":
        bloki += [
            zrzut("a02-pliki.png", "Eksplorator plików widziany przez administratora — foldery główne i lista dokumentów."),
        ]
    else:
        bloki += [
            a("<b>Widzimy wyłącznie foldery, do których nasza rola ma dostęp.</b> Jeżeli w katalogu głównym "
              "widnieje jeden folder, a lista dokumentów jest pusta, oznacza to, że dokumenty leżą wewnątrz "
              "tego folderu — wystarczy w niego wejść. Dokumenty leżące luzem w katalogu głównym są widoczne "
              "wyłącznie dla administratora, dlatego lista na tym poziomie bywa pusta."),
            zrzut("u02-pliki.png", "Katalog główny widziany przez zwykłego użytkownika — tylko udostępniony folder."),
            zrzut("u02b-folder.png", "Wnętrze udostępnionego folderu — dokumenty wraz ze statusem przetwarzania."),
        ]
    bloki += [
        n("Kolumny listy dokumentów"),
        lista(
            "<b>Ikona</b> — kolor i symbol zależą od formatu pliku, co ułatwia rozpoznanie na pierwszy rzut oka.",
            "<b>Nazwa</b> — pełna nazwa dokumentu, a pod nią jego format.",
            "<b>Rozmiar</b> — wielkość pliku.",
            "<b>Status</b> — etap przetwarzania (opisany w następnym punkcie).",
            "<b>Data dodania</b> — kiedy dokument trafił do aplikacji.",
            "<b>Akcje</b> — przyciski operacji na dokumencie.",
        ),
        n("Statusy przetwarzania"),
        tabela(["Status", "Co oznacza", "Co robić"], [
            ["W kolejce", "Dokument został zapisany i czeka na swoją kolej.",
             "Nic — wystarczy odczekać."],
            ["Przetwarzanie", "Aplikacja właśnie odczytuje treść dokumentu.",
             "Nic — przy długich dokumentach potrafi to potrwać kilka minut."],
            ["Przetworzono", "Dokument jest gotowy: można go znaleźć w wyszukiwarce i pytać o niego na czacie.",
             "Można korzystać."],
            ["Błąd przetwarzania", "Odczyt treści się nie powiódł.",
             "Zgłosić administratorowi — dokument jest w aplikacji, ale nie odpowiada na pytania."],
        ]),
        wskazowka("Status nie odświeża się sam co sekundę. Jeżeli dokument długo pozostaje „W kolejce”, "
                  "warto odświeżyć stronę przeglądarki."),
        n("Podgląd szczegółów i pobieranie"),
        a("Kliknięcie nazwy dokumentu otwiera okno ze szczegółami: format, rozmiar, status, data dodania "
          "oraz osoba, która go wgrała. Z tego okna można pobrać plik na dysk. To samo robi przycisk "
          "<b>Pobierz</b> w kolumnie akcji."),
    ]
    if rola == "admin":
        bloki.append(zrzut("a07-szczegoly.png", "Okno szczegółów dokumentu z przyciskiem pobrania."))
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
    zrzut_czat = "a08-chat.png" if rola == "admin" else "u03-chat.png"
    return [
        a("Strona <b>Baza wiedzy</b> to miejsce, w którym zadajemy pytania o treść dokumentów. Ekran dzieli się "
          "na trzy części: po lewej <b>Historia chatów</b>, pośrodku <b>Chat z bazy wiedzy</b>, a po prawej "
          "przycisk z lupą otwierający wyszukiwarkę po polach."),
        a("Pytanie wpisujemy na dole i wysyłamy klawiszem Enter albo przyciskiem <b>Wyślij</b>. "
          "Kombinacja Shift+Enter przenosi do nowej linii, jeśli chcemy zadać dłuższe pytanie."),
        zrzut(zrzut_czat, "Odpowiedź czatu z odnośnikami do źródeł w treści oraz listą dokumentów pod spodem."),
        n("Skąd wiadomo, że odpowiedź jest prawdziwa"),
        a("Aplikacja nie odpowiada „z pamięci” — buduje odpowiedź wyłącznie z fragmentów dokumentów "
          "znajdujących się w bazie. W tekście odpowiedzi widoczne są małe niebieskie numery. Każdy z nich "
          "odsyła do konkretnego dokumentu wypisanego w sekcji <b>Źródła</b> pod odpowiedzią, wraz z numerem "
          "strony. Kliknięcie numeru przewija do właściwej pozycji na liście źródeł."),
        a("Jeżeli w dokumentach nie ma odpowiedzi na zadane pytanie, aplikacja powie o tym wprost, "
          "zamiast zgadywać."),
        n("Jak pytać, żeby dostać dobrą odpowiedź"),
        lista(
            "Wystarczy sama nazwa dokumentu: wpisanie „wniosek o urlop opiekuńczy” albo „regulamin "
            "wynagradzania” daje krótkie wyjaśnienie, czym ten dokument jest, wraz z odnośnikiem do niego.",
            "Pełne zdanie działa równie dobrze: „jakie są zasady pracy zdalnej?”.",
            "Można pytać potocznie. Jeśli dokument mówi o „podróży służbowej”, a my zapytamy o „delegację”, "
            "aplikacja i tak trafi we właściwy dokument.",
            "Można pytać dalej w tej samej rozmowie — aplikacja pamięta kontekst, więc po pytaniu o zarządzenie "
            "można zapytać po prostu „a kto je podpisał?”.",
            "Pytania o listę dokumentów też działają: „wypisz wszystkie zarządzenia z 2024 roku” zwróci "
            "zestawienie dokumentów zamiast opisu ich treści.",
        ),
        n("Zmiana tematu w trakcie rozmowy"),
        a("Kiedy w środku rozmowy przechodzimy do zupełnie innej sprawy, aplikacja radzi sobie sama. "
          "Gdyby odpowiedź oparta na dotychczasowym wątku nic nie znalazła, pytanie zostaje zadane "
          "ponownie — tak, jakby padło w nowym czacie. Widać wtedy krótką informację „Nowy temat w tej "
          "rozmowie”, a zaraz po niej właściwą odpowiedź. Zakładanie nowego czatu tylko z tego powodu "
          "nie jest już potrzebne."),
        n("Historia rozmów"),
        a("Każda rozmowa zapisuje się automatycznie w panelu <b>Historia chatów</b> pod nazwą wziętą z pierwszego "
          "pytania. Kliknięcie pozycji na liście przywraca całą rozmowę. Przycisk <b>+ Nowy chat</b> zaczyna "
          "rozmowę od czysta — przydaje się, gdy chcemy oddzielić sprawy od siebie, ale przy samej zmianie "
          "tematu nie jest konieczny (zob. wyżej). Krzyżyk przy pozycji historii usuwa rozmowę."),
        wskazowka("Historia rozmów jest prywatna. Widzimy wyłącznie własne rozmowy, także administrator "
                  "nie ogląda cudzych pytań w tym panelu."),
    ]


def r_wyszukiwarka(rola):
    zrzut_wysz = "a09-wyszukiwarka.png" if rola == "admin" else "u04-wyszukiwarka.png"
    return [
        a("Czat odpowiada na pytania o <i>treść</i> dokumentów. Kiedy natomiast szukamy dokumentów po ich "
          "<i>opisie</i> — po numerze, dacie, osobie podpisującej — służy do tego <b>Wyszukiwarka po polach</b>, "
          "którą otwiera przycisk z lupą po prawej stronie ekranu Baza wiedzy."),
        zrzut(zrzut_wysz, "Wyszukiwarka po polach: pytanie po polsku oraz ręczne kryteria."),
        n("Pytanie po polsku"),
        a("Najprostszy sposób to wpisać kryteria zwykłym zdaniem w polu <i>Zapytaj po polsku</i>, na przykład "
          "„zarządzenia z 2024 roku” albo „procedury zatwierdzone przez Kisielską”. Aplikacja sama zamieni to "
          "na kryteria wyszukiwania i pokaże, jak je zrozumiała — można je potem poprawić ręcznie."),
        n("Kryteria ręczne"),
        a("Drugi sposób to złożenie warunków samodzielnie: wybieramy rodzaj dokumentu, pole opisowe, sposób "
          "porównania (równa się, zawiera, przed, po) i wpisujemy wartość. Warunki można dodawać, żeby zawęzić "
          "wynik. Wyniki pokazują nazwę dokumentu, rozpoznany rodzaj i wartości pól."),
        wskazowka("Jeżeli wyszukiwarka nie zwraca nic, mimo że dokument na pewno istnieje, warto sprawdzić dwie "
                  "rzeczy: czy ma status <i>Przetworzono</i> oraz czy szukane pole faktycznie widnieje w treści "
                  "dokumentu. Aplikacja nie wypełnia pól, których w dokumencie nie ma."),
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
         "Po piętnastu minutach bez aktywności sesja wygasa. Wystarczy zalogować się ponownie."],
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
            ["Baza wiedzy", "Część aplikacji, w której zadajemy pytania o treść dokumentów."],
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
        n("Tworzenie folderów"),
        a("Przycisk <b>+ Nowy folder</b> zakłada folder w miejscu, w którym aktualnie jesteśmy. Struktura może "
          "być zagnieżdżona dowolnie głęboko, na przykład <i>Procedury / Onkologia kliniczna / 2026</i>."),
        n("Zmiana nazwy folderu"),
        a("Ikona ołówka na kafelku folderu otwiera okno zmiany nazwy. Zmiana obejmuje automatycznie wszystkie "
          "podfoldery i dokumenty — nie trzeba nic przenosić ani wgrywać ponownie. Aplikacja nie pozwoli nadać "
          "nazwy, która już istnieje w tym samym miejscu."),
        zrzut("a05-zmiana-nazwy.png", "Zmiana nazwy folderu — operacja dostępna wyłącznie dla administratora."),
        n("Przenoszenie dokumentów"),
        a("Przycisk <b>Przenieś</b> przy dokumencie otwiera okno wyboru folderu docelowego. Lista zawiera tylko "
          "te foldery, w których wolno zapisywać."),
        zrzut("a06-przenoszenie.png", "Przenoszenie pojedynczego dokumentu do innego folderu."),
        a("Aby przenieść wiele dokumentów naraz, zaznaczamy je polami wyboru po lewej stronie listy i klikamy "
          "<b>Przenieś zaznaczone</b> nad tabelą. Przeniesienie zmienia przynależność dokumentu także dla "
          "wyszukiwania i czatu — od tej chwili obowiązują uprawnienia nowego folderu."),
        n("Usuwanie"),
        a("Przycisk <b>Usuń</b> kasuje dokument z aplikacji wraz z jego treścią przygotowaną do wyszukiwania. "
          "Folder można usunąć ikoną kosza na kafelku."),
        uwaga("Usunięcie jest nieodwracalne — dokument znika także z odpowiedzi czatu. Przy porządkach warto "
              "najpierw przenieść dokumenty do folderu archiwalnego, a usuwać dopiero po weryfikacji."),
    ]


def r_uprawnienia():
    return [
        a("Uprawnienia w aplikacji nadaje się <b>rolom, nie osobom</b>. Konto ma jedną rolę, a rola ma dostęp "
          "do wskazanych folderów. Dzięki temu przy zatrudnieniu nowej osoby wystarczy nadać jej właściwą rolę — "
          "dostępy działają od razu."),
        n("Role dostępne w aplikacji"),
        tabela(["Rola", "Typowe zastosowanie"], [
            ["Administrator", "Pełny dostęp do wszystkich folderów i do części administracyjnej."],
            ["Lekarz", "Personel lekarski — dostęp do procedur i instrukcji klinicznych."],
            ["Personel medyczny", "Pielęgniarki i pozostały personel medyczny."],
            ["Technik", "Personel techniczny."],
            ["Personel biurowy", "Administracja, kadry, sprawy pracownicze."],
            ["Gość", "Konto o najwęższym zakresie — dostęp tylko do tego, co wyraźnie udostępnione."],
        ]),
        n("Poziomy dostępu"),
        lista(
            "<b>Odczyt</b> — można przeglądać i pobierać dokumenty oraz pytać o nie na czacie.",
            "<b>Zapis</b> — dodatkowo można wgrywać, przenosić i usuwać dokumenty w tym folderze.",
        ),
        n("Nadawanie uprawnień"),
        a("Na stronie Pliki każdy kafelek folderu ma ikonę klucza. Otwiera ona okno uprawnień, w którym "
          "wybieramy rolę i poziom dostępu."),
        zrzut("a04-uprawnienia.png", "Okno uprawnień folderu — role, poziomy dostępu i uprawnienia dziedziczone."),
        uwaga("Uprawnienie nadane folderowi obowiązuje <b>także we wszystkich jego podfolderach</b>. "
              "Uprawnienia przejęte z folderu nadrzędnego są oznaczone jako „(dziedziczone)”. "
              "Dlatego dostęp nadaje się na możliwie wysokim poziomie struktury i tylko tam, gdzie trzeba — "
              "udostępnienie katalogu głównego otwiera całą bazę."),
        a("Zestawienie wszystkich nadanych uprawnień znajduje się w Administracji, na stronie "
          "<b>Lista dostępów</b>. Pozwala ona sprawdzić jednym rzutem oka, która rola ma dostęp do którego "
          "folderu, bez otwierania folderów po kolei."),
        zrzut("a11-lista-dostepow.png", "Lista dostępów — zestawienie uprawnień wszystkich ról."),
    ]


def r_administracja():
    return [
        a("Sekcja <b>Administracja</b> zawiera pięć stron przełączanych zakładkami u góry."),
        n("Użytkownicy"),
        a("Zakładanie kont, zmiana roli, ustawienie hasła oraz włączanie i wyłączanie konta. Konto wyłączone "
          "nie pozwala się zalogować, ale zachowuje historię operacji — to bezpieczniejsze niż usuwanie konta "
          "osoby, która odeszła."),
        zrzut("a10-uzytkownicy.png", "Zarządzanie kontami użytkowników."),
        n("Lista dostępów"),
        a("Zestawienie uprawnień opisane w poprzednim rozdziale."),
        n("Schematy dokumentów"),
        a("Katalog rodzajów dokumentów, które aplikacja potrafi rozpoznać. Każdy rodzaj ma nazwę, kryteria "
          "rozpoznawania opisane zwykłym językiem oraz listę pól opisowych do wyciągnięcia z dokumentu. "
          "Rodzaj można dodać, zmienić lub czasowo wyłączyć."),
        zrzut("a12-schematy.png", "Schematy dokumentów — rodzaje dokumentów wraz z polami opisowymi."),
        a("W aplikacji zdefiniowano dziesięć rodzajów dokumentów: aneks, instrukcja do procedury, porozumienie, "
          "procedura, regulamin, rozporządzenie, ustawa, wniosek, załącznik i zarządzenie."),
        n("Kolejka plików"),
        a("Podgląd przetwarzania wszystkich dokumentów: status, rozpoznany rodzaj i wyciągnięte pola. "
          "To tutaj sprawdzamy, czy partia dokumentów została poprawnie rozpoznana, i tutaj poprawiamy "
          "błędne rozpoznanie — po wskazaniu właściwego rodzaju aplikacja od nowa wyciąga pola opisowe."),
        zrzut("a13-kolejka.png", "Kolejka plików — statusy, rozpoznane rodzaje i pola dokumentów."),
        n("Ustawienia"),
        a("Parametry techniczne aplikacji: adresy usług przetwarzających dokumenty, lista dozwolonych rozszerzeń "
          "plików oraz czas automatycznego wylogowania. Lista rozszerzeń przekłada się wprost na okno wysyłki "
          "widziane przez użytkowników."),
        zrzut("a14-ustawienia.png", "Ustawienia aplikacji."),
        uwaga("Zmiany w Ustawieniach dotyczą całej aplikacji i wszystkich użytkowników. Adresy usług warto "
              "zmieniać wyłącznie w porozumieniu z wykonawcą."),
        n("Historia zmian"),
        a("Lista wersji aplikacji wraz z opisem, co zmieniła każda z nich. Otwiera ją numer wersji na dole menu."),
        zrzut("a15-historia-zmian.png", "Historia zmian aplikacji."),
    ]


def r_rozpoznawanie():
    return [
        a("Ten rozdział wyjaśnia, co aplikacja robi z dokumentem po wgraniu. Wiedza ta nie jest potrzebna do "
          "codziennej pracy, ale pomaga zrozumieć, dlaczego niektóre dokumenty opisane są bogaciej niż inne."),
        kroki(
            "<b>Odczyt treści.</b> Z dokumentu wyciągany jest tekst wraz ze strukturą — nagłówkami i tabelami. "
            "Dokumenty tekstowe (DOCX, ODT) czytane są wprost; skany i PDF-y graficzne wymagają rozpoznania pisma, "
            "co trwa dłużej.",
            "<b>Podział na fragmenty.</b> Treść dzielona jest na fragmenty tej wielkości, by dało się precyzyjnie "
            "wskazać źródło odpowiedzi — stąd numery stron przy źródłach na czacie.",
            "<b>Rozpoznanie rodzaju.</b> Na podstawie treści początku dokumentu i jego nazwy aplikacja wybiera "
            "jeden z rodzajów zdefiniowanych w Schematach dokumentów.",
            "<b>Wyciągnięcie pól.</b> Dla rozpoznanego rodzaju wyszukiwane są jego pola opisowe — na przykład "
            "dla procedury: tytuł, kod, osoby opracowujące i zatwierdzające oraz numer edycji.",
        ),
        a("Pola wypełniane są <b>wyłącznie wtedy, gdy faktycznie występują w dokumencie</b>. Dokument bez "
          "tabelki nagłówkowej będzie miał tylko część pól i jest to poprawny wynik, a nie błąd — aplikacja "
          "celowo nie zgaduje brakujących wartości."),
        wskazowka("Jeżeli rodzaj został rozpoznany błędnie, poprawiamy go w Kolejce plików. Poprawka od razu "
                  "uruchamia ponowne wyciągnięcie pól właściwych dla wskazanego rodzaju."),
    ]


def r_ograniczenia():
    return [
        a("Przekazywana wersja jest wersją demonstracyjną, przygotowaną do oceny działania aplikacji "
          "na rzeczywistych dokumentach ZCO. Warto mieć na uwadze poniższe ograniczenia."),
        lista(
            "Aplikacja odpowiada wyłącznie na podstawie dokumentów wgranych do bazy — nie zna przepisów "
            "ani wiedzy spoza nich.",
            "Odpowiedź czatu jest streszczeniem fragmentów dokumentów. Przy sprawach formalnych obowiązuje "
            "dokument źródłowy wskazany pod odpowiedzią.",
            "Rozpoznawanie rodzaju dokumentu i pól opisowych działa dobrze na dokumentach o typowej budowie; "
            "dokumenty nietypowe mogą wymagać ręcznej korekty rodzaju.",
            "Wbudowany podgląd dokumentów PDF nie jest jeszcze dostępny — dokument otwiera się po pobraniu.",
            "Powiązania między dokumentami (na przykład zarządzenie i jego załączniki) nie są jeszcze "
            "prezentowane w interfejsie.",
        ),
        a("Kolejne wersje aplikacji będą sukcesywnie usuwać te ograniczenia; każda zmiana jest opisywana "
          "w Historii zmian dostępnej z poziomu aplikacji."),
    ]


# ---------------------------------------------------------------- dokumenty

def dokument_admina():
    return [
        ("Czym jest ZCO Document Management", r_o_aplikacji()),
        ("Logowanie i układ ekranu", r_logowanie("admin")),
        ("Dashboard", r_dashboard("admin")),
        ("Twoje konto i pomoc", r_profil("admin")),
        ("Przeglądanie dokumentów", r_pliki_przegladanie("admin")),
        ("Dodawanie dokumentów", r_wgrywanie("admin")),
        ("Porządkowanie: foldery, przenoszenie, usuwanie", r_porzadkowanie()),
        ("Uprawnienia i role", r_uprawnienia()),
        ("Baza wiedzy — pytania o treść dokumentów", r_czat("admin")),
        ("Wyszukiwarka po polach opisowych", r_wyszukiwarka("admin")),
        ("Administracja", r_administracja()),
        ("Jak aplikacja rozpoznaje dokumenty", r_rozpoznawanie()),
        ("Dobre praktyki", r_dobre_praktyki("admin")),
        ("Ograniczenia wersji demonstracyjnej", r_ograniczenia()),
        ("Najczęstsze pytania", r_faq("admin")),
        ("Słowniczek", r_slowniczek()),
    ]


def dokument_uzytkownika():
    return [
        ("Czym jest ZCO Document Management", r_o_aplikacji()),
        ("Logowanie i układ ekranu", r_logowanie("user")),
        ("Dashboard", r_dashboard("user")),
        ("Twoje konto i pomoc", r_profil("user")),
        ("Przeglądanie dokumentów", r_pliki_przegladanie("user")),
        ("Dodawanie dokumentów", r_wgrywanie("user")),
        ("Baza wiedzy — pytania o treść dokumentów", r_czat("user")),
        ("Wyszukiwarka po polach opisowych", r_wyszukiwarka("user")),
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
<title>ZCO Document Management — {html.escape(tytul_wydania)}</title>
<style>{STYL}</style></head><body><div class="strona">
<div class="oklada">
  <div class="kreska"></div>
  <h1>ZCO Document Management</h1>
  <div class="wydanie">Instrukcja obsługi — {html.escape(tytul_wydania)}</div>
  <dl>
    <dt>Odbiorca</dt><dd>{ODBIORCA}</dd>
    <dt>Wykonawca</dt><dd>{WYKONAWCA}</dd>
    <dt>Wersja aplikacji</dt><dd>{WERSJA}</dd>
    <dt>Data wydania</dt><dd>{DATA}</dd>
  </dl>
  <div class="stopka">Dokument wewnętrzny. Zrzuty ekranu pochodzą z wersji demonstracyjnej
  aplikacji działającej na dokumentach ZCO.</div>
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
    katalog_zrzutow = sys.argv[1] if len(sys.argv) > 1 else os.path.join(KATALOG, "zrzuty")
    wydania = [
        ("wydanie dla administratora", dokument_admina(), "ZCO-DM-instrukcja-administratora"),
        ("wydanie dla użytkownika", dokument_uzytkownika(), "ZCO-DM-instrukcja-uzytkownika"),
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
