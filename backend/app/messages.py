"""Komunikaty błędów backendu w języku interfejsu.

Skąd ten kształt. Komunikat powstaje GŁĘBOKO w routerze — tam, gdzie wychodzi błąd
— a język żądania znany jest na jego brzegu. Przekazywanie języka do każdej funkcji,
która potrafi rzucić wyjątkiem, oznaczałoby dodatkowy argument w kilkudziesięciu
miejscach i pilnowanie go w nieskończoność.

Dlatego router podaje KLUCZ (`Message("files.notFound")`), a tłumaczenie dokłada się
raz, przy zamianie wyjątku na odpowiedź (`app/main.py`). Na drut idzie zwykły napis,
więc dla frontendu i dla każdego innego klienta nic się nie zmienia.

Dlaczego tłumaczy BACKEND, a nie front. Front musiałby rozpoznać kod błędu w każdym
miejscu, gdzie pokazuje `err.message` — a jest ich kilkadziesiąt. Tutaj wystarczy
jeden nagłówek z żądania.

Co ZOSTAJE po polsku (świadomie): komunikaty techniczne, których nie zobaczy
użytkownik — błędy uwierzytelniania między usługami, komunikaty dla osoby stawiającej
wdrożenie („uruchom seed.sql"), pomyłki w użyciu API. Ich tłumaczenie byłoby pracą bez
odbiorcy, a w logu zawsze wygodniej mieć jedno brzmienie.
"""

from app.locales import BASE_LOCALE, normalize_locale

# Fragment nazwy klucza → sekcja. Klucze mają postać „obszar.nazwa”.
KATALOG: dict[str, dict[str, str]] = {
    "pl": {
        # ---------------------------------------------------------- wspólne
        "common.adminOnly": "Tylko administrator.",
        "common.noPermission": "Brak uprawnień.",
        "common.userNotFound": "Użytkownik nie znaleziony.",
        "common.emptyName": "Nazwa nie może być pusta.",
        # ------------------------------------------------------------ konto
        "auth.userExists": "Użytkownik z podanym adresem e-mail lub nazwą już istnieje.",
        "auth.noCredentials": "Brak danych logowania.",
        "auth.badCredentials": "Nieprawidłowy adres e-mail lub hasło.",
        "auth.inactive": "Użytkownik jest nieaktywny.",
        "auth.inactiveOrMissing": "Użytkownik nie istnieje albo jest nieaktywny.",
        "auth.usernameTooShort": "Nazwa użytkownika musi mieć co najmniej 3 znaki.",
        "auth.usernameTooLong": "Nazwa użytkownika może mieć najwyżej 100 znaków.",
        "auth.usernameTaken": "Ta nazwa użytkownika jest już zajęta.",
        "auth.usernameTakenByOther": "Ta nazwa użytkownika jest już zajęta przez inne konto.",
        "auth.badEmail": "Podaj poprawny adres e-mail.",
        "auth.emailTaken": "Ten adres e-mail jest już używany przez inne konto.",
        "auth.emailTakenByOther": "Ten adres e-mail jest już zajęty przez inne konto.",
        "auth.fullNameTooLong": "Imię i nazwisko może mieć najwyżej 200 znaków.",
        "auth.wrongCurrentPassword": "Aktualne hasło jest nieprawidłowe.",
        "auth.samePassword": "Nowe hasło musi różnić się od dotychczasowego.",
        "auth.passwordTooShort": "Nowe hasło musi mieć co najmniej {min} znaków.",
        "auth.unsupportedLocale": "Nieobsługiwany język interfejsu. Dostępne: {lista}.",
        # ------------------------------------------------------------ pliki
        "files.rootUploadAdminOnly": "Wgrywanie do katalogu głównego jest zarezerwowane dla administratora.",
        "files.noWriteHere": "Brak uprawnień do zapisu w tym folderze.",
        "files.tooLarge": "Plik jest za duży. Maksymalny rozmiar to {limit}.",
        "files.empty": "Plik jest pusty.",
        "files.notFound": "Plik nie istnieje.",
        "files.notFoundOnDisk": "Plik nie istnieje na dysku.",
        "files.noAccess": "Brak dostępu do tego pliku.",
        "files.noDeletePermission": "Brak uprawnień do usunięcia tego pliku.",
        "files.noneSelected": "Nie wskazano plików.",
        "files.noneSelectedToMove": "Nie wskazano plików do przeniesienia.",
        "files.targetFolderMissing": "Folder docelowy nie istnieje.",
        "files.noWriteInTarget": "Brak prawa zapisu w folderze docelowym.",
        "files.moveToRootAdminOnly": "Tylko administrator może przenosić do katalogu głównego.",
        "files.categoryAdminOnly": "Tylko administrator może zmieniać kategorię.",
        "files.updateAdminOnly": "Tylko administrator może aktualizować pliki.",
        "files.emptyList": "Pusta lista dokumentów.",
        "files.listTooLong": "Lista jest za długa (maks. {limit}).",
        "files.nothingToExport": "Brak dokumentów do wyeksportowania.",
        # --------------------------------------------------------- foldery
        "folders.notFound": "Folder nie istnieje.",
        "folders.noAccess": "Brak dostępu do tego folderu.",
        "folders.nameExists": "Folder o podanej nazwie już istnieje.",
        "folders.nameWithSlash": "Nazwa nie może zawierać ukośnika.",
        "folders.createAdminOnly": "Tylko administrator może tworzyć foldery.",
        "folders.deleteAdminOnly": "Tylko administrator może usuwać foldery.",
        "folders.renameAdminOnly": "Tylko administrator może zmieniać nazwę folderu.",
        "folders.permissionsAdminOnly": "Tylko administrator może zarządzać uprawnieniami.",
        "folders.setPermissionAdminOnly": "Tylko administrator może ustawiać uprawnienia.",
        "folders.deletePermissionAdminOnly": "Tylko administrator może usuwać uprawnienia.",
        "folders.permissionNotFound": "Uprawnienie nie istnieje.",
        "folders.accessListAdminOnly": "Tylko administrator może przeglądać listę dostępów.",
        # ------------------------------------------------------------- role
        "roles.adminOnly": "Tylko administrator może zarządzać rolami.",
        "roles.nameTooShort": "Nazwa roli musi mieć co najmniej 2 znaki.",
        "roles.nameTooLong": "Nazwa roli może mieć najwyżej 100 znaków.",
        "roles.nameNeedsChars": "Nazwa roli musi zawierać litery lub cyfry.",
        "roles.cannotMoveToDeleted": "Nie można przenieść użytkowników do roli, która jest usuwana.",
        # -------------------------------------------------------- schematy
        "schemas.adminOnly": "Tylko administrator może zarządzać schematami.",
        "schemas.notFound": "Schemat nie istnieje.",
        "schemas.badSlug": "Identyfikator: 2–50 znaków (małe litery, cyfry, myślnik, podkreślnik).",
        "schemas.badPattern": "Wzorzec nazwy musi zawierać choć jedno pole w nawiasach, np. {przyklad}.",
        # --------------------------------------------------------- kolejka
        "queue.notFound": "Element kolejki nie istnieje.",
        # ------------------------------------------------------------ czat
        "chat.conversationNotFound": "Rozmowa nie istnieje.",
        "chat.emptyQuery": "Puste zapytanie.",
        "chat.queryNotUnderstood": "Nie udało się zrozumieć zapytania.",
        "chat.webhookMissing": "Adres webhooka czatu nie jest skonfigurowany (Ustawienia aplikacji).",
        "chat.perUserAdminOnly": "Tylko administrator widzi podział na użytkowników.",
        "chat.unknownRating": "Nieznana ocena: {ocena}",
        # ------------------------------------------------------- ustawienia
        "settings.adminOnly": "Tylko administrator może zmieniać ustawienia.",
        "settings.iconAdminOnly": "Tylko administrator może zmieniać ikonę.",
        "settings.appNameLength": "Nazwa aplikacji: od 1 do 40 znaków.",
        "settings.badColor": "Kolor podaj w zapisie szesnastkowym, np. #1fc8ba.",
        "settings.extensionsFormat": "Rozszerzenia mogą zawierać tylko litery i cyfry, rozdzielone przecinkami.",
        "settings.extensionsEmpty": "Podaj co najmniej jedno rozszerzenie (np. pdf,docx,xlsx).",
        "settings.idleNotNumber": "Czas bezczynności musi być liczbą minut.",
        "settings.smtpPortNotNumber": "Port SMTP musi być liczbą.",
        "settings.smtpPortRange": "Port SMTP musi mieścić się w zakresie 1–65535.",
        "settings.systemStatusAdminOnly": "Stan serwera widzi tylko administrator.",
        # ----------------------------------------------------------- ikona
        "branding.iconType": "Ikona musi być plikiem PNG albo SVG.",
        "branding.iconTooSmall": "Ikona jest za mała — zalecane minimum to 128×128 px.",
        "branding.notPng": "To nie jest prawidłowy plik PNG.",
        "branding.notSvg": "To nie jest prawidłowy plik SVG.",
        "branding.iconTooBig": "Ikona może mieć najwyżej {limit} kB.",
        "branding.iconNotSquare": "Ikona musi być kwadratowa (proporcje 1:1); ten plik ma {wymiary}.",
        # --------------------------------------------------------- kontakt
        "contact.tooShort": "Opisz zgłoszenie w co najmniej 10 znakach.",
        "contact.tooLong": "Zgłoszenie może mieć najwyżej {limit} znaków.",
        "contact.mailNotConfigured": "Wysyłka zgłoszeń nie jest skonfigurowana — uzupełnij dane poczty w Ustawieniach aplikacji.",
        "contact.sendFailed": "Nie udało się wysłać zgłoszenia. Administrator znajdzie powód w logu aplikacji.",
        # ------------------------------------------------------ tłumaczenia
        "translations.adminOnly": "Tylko administrator może zmieniać tłumaczenia.",
        "translations.baseLocale": "Polski jest językiem bazowym — jego teksty zmienia się w kodzie, nie tutaj.",
        "translations.emptyKey": "Pusty klucz.",
        "translations.keyTooLong": "Klucz może mieć najwyżej 200 znaków.",
        "translations.tooMany": "Najwyżej {limit} napisów naraz.",
        "translations.unsupported": "Nieobsługiwany język. Dostępne: {lista}.",
    },
    "en": {
        "common.adminOnly": "Administrators only.",
        "common.noPermission": "No permission.",
        "common.userNotFound": "User not found.",
        "common.emptyName": "The name cannot be empty.",

        "auth.userExists": "A user with this e-mail address or name already exists.",
        "auth.noCredentials": "No sign-in details provided.",
        "auth.badCredentials": "Incorrect e-mail address or password.",
        "auth.inactive": "The user is inactive.",
        "auth.inactiveOrMissing": "The user does not exist or is inactive.",
        "auth.usernameTooShort": "The user name must be at least 3 characters.",
        "auth.usernameTooLong": "The user name may be at most 100 characters.",
        "auth.usernameTaken": "That user name is already taken.",
        "auth.usernameTakenByOther": "That user name is already taken by another account.",
        "auth.badEmail": "Enter a valid e-mail address.",
        "auth.emailTaken": "That e-mail address is already used by another account.",
        "auth.emailTakenByOther": "That e-mail address is already taken by another account.",
        "auth.fullNameTooLong": "The full name may be at most 200 characters.",
        "auth.wrongCurrentPassword": "The current password is incorrect.",
        "auth.samePassword": "The new password must differ from the current one.",
        "auth.passwordTooShort": "The new password must be at least {min} characters.",
        "auth.unsupportedLocale": "Unsupported interface language. Available: {lista}.",

        "files.rootUploadAdminOnly": "Uploading to the root folder is reserved for administrators.",
        "files.noWriteHere": "No write permission in this folder.",
        "files.tooLarge": "The file is too large. The maximum size is {limit}.",
        "files.empty": "The file is empty.",
        "files.notFound": "The file does not exist.",
        "files.notFoundOnDisk": "The file is missing from disk.",
        "files.noAccess": "No access to this file.",
        "files.noDeletePermission": "No permission to delete this file.",
        "files.noneSelected": "No files selected.",
        "files.noneSelectedToMove": "No files selected to move.",
        "files.targetFolderMissing": "The target folder does not exist.",
        "files.noWriteInTarget": "No write permission in the target folder.",
        "files.moveToRootAdminOnly": "Only an administrator can move files to the root folder.",
        "files.categoryAdminOnly": "Only an administrator can change the category.",
        "files.updateAdminOnly": "Only an administrator can update files.",
        "files.emptyList": "The document list is empty.",
        "files.listTooLong": "The list is too long (max {limit}).",
        "files.nothingToExport": "No documents to export.",

        "folders.notFound": "The folder does not exist.",
        "folders.noAccess": "No access to this folder.",
        "folders.nameExists": "A folder with that name already exists.",
        "folders.nameWithSlash": "The name cannot contain a slash.",
        "folders.createAdminOnly": "Only an administrator can create folders.",
        "folders.deleteAdminOnly": "Only an administrator can delete folders.",
        "folders.renameAdminOnly": "Only an administrator can rename folders.",
        "folders.permissionsAdminOnly": "Only an administrator can manage permissions.",
        "folders.setPermissionAdminOnly": "Only an administrator can grant permissions.",
        "folders.deletePermissionAdminOnly": "Only an administrator can remove permissions.",
        "folders.permissionNotFound": "The permission does not exist.",
        "folders.accessListAdminOnly": "Only an administrator can view the access list.",

        "roles.adminOnly": "Only an administrator can manage roles.",
        "roles.nameTooShort": "The role name must be at least 2 characters.",
        "roles.nameTooLong": "The role name may be at most 100 characters.",
        "roles.nameNeedsChars": "The role name must contain letters or digits.",
        "roles.cannotMoveToDeleted": "Users cannot be moved to the role being deleted.",

        "schemas.adminOnly": "Only an administrator can manage schemas.",
        "schemas.notFound": "The schema does not exist.",
        "schemas.badSlug": "Identifier: 2–50 characters (lower-case letters, digits, hyphen, underscore).",
        "schemas.badPattern": "The name pattern must contain at least one field in braces, e.g. {przyklad}.",

        "queue.notFound": "The queue item does not exist.",

        "chat.conversationNotFound": "The conversation does not exist.",
        "chat.emptyQuery": "Empty query.",
        "chat.queryNotUnderstood": "Could not understand the query.",
        "chat.webhookMissing": "The chat webhook address is not configured (Application settings).",
        "chat.perUserAdminOnly": "Only an administrator sees the per-user breakdown.",
        "chat.unknownRating": "Unknown rating: {ocena}",

        "settings.adminOnly": "Only an administrator can change the settings.",
        "settings.iconAdminOnly": "Only an administrator can change the icon.",
        "settings.appNameLength": "Application name: 1 to 40 characters.",
        "settings.badColor": "Give the colour in hexadecimal, e.g. #1fc8ba.",
        "settings.extensionsFormat": "Extensions may contain only letters and digits, separated by commas.",
        "settings.extensionsEmpty": "Give at least one extension (e.g. pdf,docx,xlsx).",
        "settings.idleNotNumber": "The idle time must be a number of minutes.",
        "settings.smtpPortNotNumber": "The SMTP port must be a number.",
        "settings.smtpPortRange": "The SMTP port must be between 1 and 65535.",
        "settings.systemStatusAdminOnly": "Only an administrator can see the server status.",

        "branding.iconType": "The icon must be a PNG or SVG file.",
        "branding.iconTooSmall": "The icon is too small — 128×128 px is the recommended minimum.",
        "branding.notPng": "This is not a valid PNG file.",
        "branding.notSvg": "This is not a valid SVG file.",
        "branding.iconTooBig": "The icon may be at most {limit} kB.",
        "branding.iconNotSquare": "The icon must be square (1:1); this file is {wymiary}.",

        "contact.tooShort": "Describe the request in at least 10 characters.",
        "contact.tooLong": "The request may be at most {limit} characters.",
        "contact.mailNotConfigured": "Sending requests is not configured — fill in the mail settings in Application settings.",
        "contact.sendFailed": "Could not send the request. An administrator will find the reason in the application log.",

        "translations.adminOnly": "Only an administrator can change translations.",
        "translations.baseLocale": "Polish is the base language — its texts are changed in the code, not here.",
        "translations.emptyKey": "Empty key.",
        "translations.keyTooLong": "The key may be at most 200 characters.",
        "translations.tooMany": "At most {limit} strings at a time.",
        "translations.unsupported": "Unsupported language. Available: {lista}.",
    },
}


class UserMessage:
    """Klucz komunikatu dla UŻYTKOWNIKA wraz z wartościami do podstawienia.

    Nazwa z przedrostkiem, bo samo  to w tym projekcie model wiadomości
    czatu z bazy — dwie takie nazwy w jednym module dają cichą kolizję importów.

    Podaje się go jako `detail` wyjątku; na napis zamienia go dopiero obsługa
    wyjątku, która zna język żądania (zob. `app/main.py`).
    """

    __slots__ = ("key", "params")

    def __init__(self, key: str, **params: object) -> None:
        self.key = key
        self.params = params

    def __repr__(self) -> str:            # przydaje się w logach i testach
        return f"UserMessage({self.key!r}, {self.params!r})"


def render(message: UserMessage, locale: str | None = None) -> str:
    """Komunikat po polsku albo w języku żądania.

    Brak tłumaczenia = tekst polski. Brak klucza w ogóle = sam klucz; to znaczy,
    że ktoś dodał komunikat i zapomniał o wpisie — widać to od razu, a żądanie
    kończy się normalnym błędem, a nie wyjątkiem w obsłudze wyjątku.
    """
    kod = normalize_locale(locale) or BASE_LOCALE
    wzorzec = KATALOG.get(kod, {}).get(message.key) or KATALOG[BASE_LOCALE].get(message.key)
    if wzorzec is None:
        return message.key
    try:
        return wzorzec.format(**message.params)
    except (KeyError, IndexError):
        # Niezgodność pól nie może wywrócić odpowiedzi — pokazujemy wzorzec.
        return wzorzec
