"""Buduje konfiguracje dla shot.py i uruchamia zrzuty dla obu wdrożeń.

Uruchomienie:
    python zrzuty_config.py [zco|hirs] [admin|user] [pl|en|cs|de|es|uk]

Bez argumentów robi wszystkie 24 przebiegi (2 wdrożenia x 2 wydania x 6 języków). Tokeny sesji generuje po stronie
serwera (kod aplikacji, `hash`/`create_access_token`) — nigdzie nie pojawia się
hasło, a konta nie są zakładane ani modyfikowane na potrzeby zrzutów.

Zrzuty lądują w `zrzuty/<wdrożenie>/<język>/`, skąd bierze je `generuj.py`.
"""
import json
import os
import subprocess
import sys

KATALOG = os.path.dirname(os.path.abspath(__file__))
SPARK = "marcin@192.168.1.34"

# Etykiety przycisków bierzemy Z KATALOGU APLIKACJI, a nie wpisujemy tutaj.
# Skrypt klika po treści przycisku („Prześlij pliki"), więc w obcym języku
# wpisany na sztywno polski napis po prostu nie trafia — a zrzut wychodzi
# wtedy bez okna dialogowego i nikt tego nie zauważa aż do korekty PDF-a.
# Dzięki wspólnemu źródłu zmiana nazwy przycisku przenosi się tu sama.
KATALOGI_NAPISOW = os.path.join(KATALOG, "..", "..", "frontend", "messages")
_napisy = {}


def napis(jezyk, klucz):
    """Napis aplikacji w danym języku, np. napis("de", "files.uploadButton")."""
    if jezyk not in _napisy:
        with open(os.path.join(KATALOGI_NAPISOW, f"{jezyk}.json"), encoding="utf-8") as f:
            _napisy[jezyk] = json.load(f)
    biezacy = _napisy[jezyk]
    for czesc in klucz.split("."):
        biezacy = biezacy[czesc]
    return biezacy

# Konta użyte na zrzutach. Administrator i konto bez uprawnień administracyjnych —
# każde wydanie instrukcji pokazuje aplikację tak, jak widzi ją jego odbiorca.
WDROZENIA = {
    "zco": {
        "origin": "http://192.168.1.34:3000",
        "baza": "edmdatabase",
        "kontener": "edm-backend",
        "konta": {"admin": 20, "user": 19},
    },
    "hirs": {
        "origin": "http://192.168.1.34:3001",
        "baza": "hirsdatabase",
        "kontener": "hirs-backend",
        "konta": {"admin": 20, "user": 22},
    },
}

# Foldery, w których robimy zrzuty operacji na plikach — muszą zawierać dokumenty
# i dawać prawo zapisu. Podajemy fragment ścieżki; skrypt znajdzie pierwszy pasujący.
# Folder MUSI zawierać dokumenty bezpośrednio (nie same podfoldery) — inaczej
# nie ma czego kliknąć przy zrzutach szczegółów, przenoszenia i nadawania nazw.
FOLDER_ROBOCZY = {"zco": "Regulamin pracy", "hirs": "Faktury"}
# Języki interfejsu — ta sama lista, co w aplikacji i w generatorze instrukcji.
JEZYKI = ["pl", "en", "cs", "de", "es", "uk"]
# Folder udostępniony roli konta użytkownika — inny niż powyżej, bo zwykłe
# konto widzi tylko część zbioru.
FOLDER_UZYTKOWNIKA = {"zco": "Praca zdalna", "hirs": "Normy i standardy"}

# Pytanie na zrzucie czatu pada w JĘZYKU ZRZUTU — dokumenty są polskie, ale
# wyszukiwanie działa międzyjęzykowo (bge-m3), a odpowiedź i tak powstaje
# w języku interfejsu. Polskie pytanie obok niemieckiej odpowiedzi wyglądałoby
# w niemieckiej instrukcji jak usterka.
PYTANIE = {
    "zco": {
        "pl": "Od jakiego wieku dziecka przysługuje dofinansowanie do wypoczynku?",
        "en": "From what age of a child is the holiday subsidy available?",
        "cs": "Od jakého věku dítěte náleží příspěvek na rekreaci?",
        "de": "Ab welchem Alter des Kindes steht der Erholungszuschuss zu?",
        "es": "¿A partir de qué edad del niño corresponde la ayuda para vacaciones?",
        "uk": "З якого віку дитини належить доплата на відпочинок?",
    },
    "hirs": {
        "pl": "Jakie normy obowiązują przy przechowywaniu dokumentacji?",
        "en": "What standards apply to storing documentation?",
        "cs": "Jaké normy platí pro uchovávání dokumentace?",
        "de": "Welche Normen gelten für die Aufbewahrung von Unterlagen?",
        "es": "¿Qué normas rigen la conservación de la documentación?",
        "uk": "Які норми діють щодо зберігання документації?",
    },
}
# Wyszukiwarka rozpoznaje z pytania RODZAJ dokumentu, a rodzaje są nazwane po
# polsku w schematach. Pytanie w obcym języku i tak trafia — model dopasowuje
# nazwę rodzaju — ale zostawiamy krótką formę, żeby wynik mieścił się w kadrze.
# Pytania „tła" — zadawane przed zrzutem czatu, każde w nowej rozmowie, żeby
# pasek historii wyglądał jak u kogoś, kto z aplikacji korzysta. Krótkie, bo
# tytułem rozmowy jest całe pytanie, a pasek jest wąski.
PYTANIA_TLA = {
    "zco": {
        "pl": ["Jakie są zasady pracy zdalnej?", "Ile dni urlopu na żądanie?",
               "Kto zatwierdza wnioski urlopowe?"],
        "en": ["What are the rules on remote work?", "How many days of on-demand leave?",
               "Who approves leave applications?"],
        "cs": ["Jaká jsou pravidla práce na dálku?", "Kolik dní dovolené na zavolání?",
               "Kdo schvaluje žádosti o dovolenou?"],
        "de": ["Wie sind die Regeln zur Telearbeit?", "Wie viele Tage Urlaub auf Abruf?",
               "Wer genehmigt Urlaubsanträge?"],
        "es": ["¿Cuáles son las normas del trabajo a distancia?",
               "¿Cuántos días de permiso a demanda?",
               "¿Quién aprueba las solicitudes de vacaciones?"],
        "uk": ["Які правила дистанційної роботи?", "Скільки днів відпустки на вимогу?",
               "Хто затверджує заяви на відпустку?"],
    },
    "hirs": {
        "pl": ["Jakie normy dotyczą dezynfekcji?", "Co zawiera dokumentacja produktu?",
               "Jak przechowywać faktury?"],
        "en": ["What standards apply to disinfection?",
               "What does the product documentation contain?",
               "How should invoices be stored?"],
        "cs": ["Jaké normy platí pro dezinfekci?", "Co obsahuje dokumentace produktu?",
               "Jak uchovávat faktury?"],
        "de": ["Welche Normen gelten für die Desinfektion?",
               "Was enthält die Produktdokumentation?", "Wie sind Rechnungen aufzubewahren?"],
        "es": ["¿Qué normas rigen la desinfección?",
               "¿Qué contiene la documentación del producto?",
               "¿Cómo se conservan las facturas?"],
        "uk": ["Які норми стосуються дезінфекції?", "Що містить документація продукту?",
               "Як зберігати рахунки?"],
    },
}
PYTANIE_WYSZUKIWARKI = {
    "zco": {
        "pl": "wszystkie zarządzenia z 2023 roku",
        "en": "all orders from 2023",
        "cs": "všechna nařízení z roku 2023",
        "de": "alle Verordnungen aus dem Jahr 2023",
        "es": "todos los reglamentos de 2023",
        "uk": "усі розпорядження з 2023 року",
    },
    "hirs": {
        "pl": "wszystkie faktury", "en": "all invoices", "cs": "všechny faktury",
        "de": "alle Rechnungen", "es": "todas las facturas", "uk": "усі рахунки",
    },
}

# --- pomocnicze wyrażenia JS -------------------------------------------------
KLIK_TEKST = "[...document.querySelectorAll('button,a')].find(e=>e.textContent.trim().includes({t}))?.click()"
KLIK_TYTUL = "document.querySelector('[title={t}]')?.click()"
OKNO = ".fixed.inset-0 > div"


def js_klik(tekst):
    return KLIK_TEKST.replace("{t}", json.dumps(tekst))


def js_tytul(tytul):
    return KLIK_TYTUL.replace("{t}", json.dumps(tytul))


def js_wejdz_do_folderu(fragment):
    """Wejście do folderu po fragmencie nazwy — kafelek albo wiersz listy."""
    return (
        "(() => { const f=" + json.dumps(fragment) + ";"
        " const k=[...document.querySelectorAll('button,tr')]"
        "   .find(e=>e.textContent.includes(f) && (e.closest('.grid')||e.tagName==='TR'));"
        " if(k) k.click(); return !!k; })()"
    )


def kroki_tla(w, j):
    """Trzy rozmowy w języku zrzutu, każda zaczęta od nowa.

    Odpowiedź czeka 60 s — tyle wystarcza na krótkie pytanie. Gdyby model nie
    zdążył, rozmowa i tak powstaje z właściwym tytułem, a o to tu chodzi.
    """
    kroki = []
    for pytanie in PYTANIA_TLA[w][j]:
        kroki.append({"js": js_wpisz("textarea", pytanie) + ";" + js_klik(napis(j, "chat.send")),
                      "wait": 60})
        kroki.append({"js": js_klik(napis(j, "chat.newChat")), "wait": 2.5})
    return kroki


def js_wpisz(selektor, tekst):
    """Wpisanie tekstu tak, żeby React zobaczył zmianę (setter z prototypu)."""
    return (
        "(() => { const e=document.querySelector(" + json.dumps(selektor) + ");"
        " if(!e) return false;"
        " const proto = e.tagName==='TEXTAREA' ? HTMLTextAreaElement : HTMLInputElement;"
        " Object.getOwnPropertyDescriptor(proto.prototype,'value').set"
        "   .call(e, " + json.dumps(tekst) + ");"
        " e.dispatchEvent(new Event('input',{bubbles:true})); return true; })()"
    )


def zrzuty_admina(w, katalog, j):
    """Lista zrzutów wydania administratora. `w` — wdrożenie, `j` — język."""
    p = lambda nazwa: os.path.join(katalog, nazwa)
    folder = FOLDER_ROBOCZY[w]
    # Pole pytania rozpoznajemy po PEŁNEJ podpowiedzi z katalogu — prefiks „np."
    # jest w każdym języku inny.
    pole_nl = f'input[placeholder="{napis(j, "search.askPlaceholder")}"]'
    return [
        {"path": "/login", "out": p("a00-logowanie.png"), "wyloguj": True, "wait": 3},
        {"path": "/dashboard", "out": p("a01-pulpit.png"), "wait": 6},
        {"path": "/dashboard", "out": p("a19-panele.png"), "wait": 6,
         "js": "[...document.querySelectorAll('h3')].find(h=>h.textContent.includes("
               + json.dumps(napis(j, "dashboard.quickActions")) + "))?.scrollIntoView({block:'center'})",
         "clip_js": "[...document.querySelectorAll('h3')].find(h=>h.textContent.includes("
                    + json.dumps(napis(j, "dashboard.quickActions")) + "))?.closest('div.grid')", "pad": 10},
        {"path": "/dashboard/files", "out": p("a02-pliki.png"), "wait": 5},
        {"path": "/dashboard/files", "out": p("a02b-kafelki.png"), "wait": 5,
         "js": "[...document.querySelectorAll(" + json.dumps(f'[aria-label="{napis(j, "files.listViewLabel")}"] button')
               + ")].find(b=>b.textContent.includes(" + json.dumps(napis(j, "files.viewGrid")) + "))?.click()",
         "wait_js": 1.5},
        {"path": "/dashboard/files", "out": p("a03-wysylka.png"), "wait": 5,
         "js": js_klik(napis(j, "files.uploadButton")), "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a04-uprawnienia.png"), "wait": 5,
         "js": js_tytul(napis(j, "files.permTitle")), "wait_js": 2.0, "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a05-zmiana-nazwy.png"), "wait": 5,
         "js": js_tytul(napis(j, "files.renameFolder")), "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a07-szczegoly.png"), "wait": 5,
         "js": js_wejdz_do_folderu(folder), "wait_js": 3.5,
         "js2": "document.querySelector('tbody tr')?.click()", "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a06-przenoszenie.png"), "wait": 5,
         "js": js_wejdz_do_folderu(folder), "wait_js": 3.5,
         "js2": js_tytul(napis(j, "files.moveToFolder")), "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a20-nazwy.png"), "wait": 5,
         "js": js_wejdz_do_folderu(folder), "wait_js": 3.5,
         "js2": "[...document.querySelectorAll('tbody input[type=checkbox]')].slice(0,4)"
                ".forEach(c=>c.click());"
                "[...document.querySelectorAll('button')].find(b=>b.textContent.includes("
                + json.dumps(napis(j, "files.bulkAction")) + "))?.click();",
         "js3": "[...document.querySelectorAll('button')].find(b=>b.textContent.includes("
                + json.dumps(napis(j, "files.bulkRename")) + "))?.click()",
         "wait_js3": 4.0, "clip": OKNO},
        {"path": "/dashboard/chat", "out": p("a08-chat.png"), "wait": 5,
         "kroki": kroki_tla(w, j),
         "js": js_wpisz("textarea", PYTANIE[w][j]) + ";" + js_klik(napis(j, "chat.send")), "wait_js": 95,
         "js2": "(() => { const o=[...document.querySelectorAll('div')]"
               ".find(d=>d.className.includes('overflow-y-auto') "
               "&& d.className.includes('space-y-4'));"
               " if(o) o.scrollTop=o.scrollHeight; })()", "wait_js2": 2.0,
         },
        {"path": "/dashboard/wyszukiwanie", "out": p("a09-wyszukiwarka.png"), "wait": 4,
         "js": js_wpisz(pole_nl, PYTANIE_WYSZUKIWARKI[w][j]) + ";" + js_klik(napis(j, "search.askButton")),
         "wait_js": 12},
        {"path": "/dashboard/users", "out": p("a10-uzytkownicy.png"), "wait": 4},
        {"path": "/dashboard/access-list", "out": p("a11-lista-dostepow.png"), "wait": 4},
        {"path": "/dashboard/access-list", "out": p("a11b-rola.png"), "wait": 4,
         "js": js_klik(napis(j, "access.addRole")), "clip": OKNO},
        {"path": "/dashboard/doc-schemas", "out": p("a12-schematy.png"), "wait": 4},
        {"path": "/dashboard/file-queue", "out": p("a13-kolejka.png"), "wait": 5},
        {"path": "/dashboard/settings", "out": p("a14-ustawienia.png"), "wait": 4},
        {"path": "/dashboard/changelog", "out": p("a15-historia-zmian.png"), "wait": 4},
        {"path": "/dashboard/profil", "out": p("a16-profil.png"), "wait": 4},
        {"path": "/dashboard/pomoc", "out": p("a17-pomoc.png"), "wait": 6},
        {"path": "/dashboard", "out": p("a18-menu-awatara.png"), "wait": 4,
         "js": "document.querySelector('header button')?.click()", "clip": "header"},
        {"path": "/dashboard/kontakt", "out": p("a21-kontakt.png"), "wait": 4},
    ]


def zrzuty_uzytkownika(w, katalog, j):
    p = lambda nazwa: os.path.join(katalog, nazwa)
    pole_nl = f'input[placeholder="{napis(j, "search.askPlaceholder")}"]'
    return [
        {"path": "/login", "out": p("u00-logowanie.png"), "wyloguj": True, "wait": 3},
        {"path": "/dashboard", "out": p("u01-pulpit.png"), "wait": 6},
        {"path": "/dashboard/files", "out": p("u02-pliki.png"), "wait": 5},
        {"path": "/dashboard/files", "out": p("u02b-folder.png"), "wait": 5,
         "js": js_wejdz_do_folderu(FOLDER_UZYTKOWNIKA[w]), "wait_js": 3.5},
        {"path": "/dashboard/chat", "out": p("u03-chat.png"), "wait": 5,
         "kroki": kroki_tla(w, j),
         "js": js_wpisz("textarea", PYTANIE[w][j]) + ";" + js_klik(napis(j, "chat.send")), "wait_js": 95,
         "js2": "(() => { const o=[...document.querySelectorAll('div')]"
               ".find(d=>d.className.includes('overflow-y-auto') "
               "&& d.className.includes('space-y-4'));"
               " if(o) o.scrollTop=o.scrollHeight; })()", "wait_js2": 2.0,
         },
        {"path": "/dashboard/wyszukiwanie", "out": p("u04-wyszukiwarka.png"), "wait": 4,
         "js": js_wpisz(pole_nl, PYTANIE_WYSZUKIWARKI[w][j]) + ";" + js_klik(napis(j, "search.askButton")),
         "wait_js": 12},
        {"path": "/dashboard/profil", "out": p("u05-profil.png"), "wait": 4},
        {"path": "/dashboard/pomoc", "out": p("u06-pomoc.png"), "wait": 6},
        {"path": "/dashboard/kontakt", "out": p("u07-kontakt.png"), "wait": 4},
    ]


def sesja(wdrozenie, user_id):
    """Token i dane konta prosto z serwera — bez podawania hasła."""
    kod = (
        "from app.database import SessionLocal;"
        "from app.models import User;"
        "from app.auth.jwt_handler import create_access_token;"
        "import json;"
        "db=SessionLocal();"
        f"u=db.query(User).get({user_id});"
        "print(json.dumps({'token': create_access_token("
        "{'sub': str(u.id), 'username': u.username, 'role': u.role}),"
        "'user': {'id': u.id, 'email': u.email, 'username': u.username,"
        "'full_name': u.full_name, 'role': u.role, 'is_active': u.is_active,"
        "'is_admin': u.is_admin, 'created_at': str(u.created_at),"
        "'updated_at': str(u.updated_at), 'last_login': str(u.last_login)}}))"
    )
    kontener = WDROZENIA[wdrozenie]["kontener"]
    wynik = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", SPARK, f"docker exec {kontener} python -c {json.dumps(kod)}"],
        capture_output=True, text=True, check=True, encoding="utf-8",
    )
    return json.loads(wynik.stdout.strip().splitlines()[-1])


def przebieg(wdrozenie, wydanie, jezyk):
    cfgw = WDROZENIA[wdrozenie]
    # Osobny katalog na język — zrzuty różnią się wyłącznie napisami interfejsu,
    # ale to właśnie one są powodem, dla którego instrukcja ma sześć wydań.
    katalog = os.path.join(KATALOG, "zrzuty", wdrozenie, jezyk)
    os.makedirs(katalog, exist_ok=True)
    s = sesja(wdrozenie, cfgw["konta"][wydanie])
    shots = (zrzuty_admina if wydanie == "admin" else zrzuty_uzytkownika)(wdrozenie, katalog, jezyk)

    # Ekran Pomoc pokazuje instrukcję, więc jego zrzut ma sens dopiero PO wdrożeniu
    # nowego wydania — inaczej w ramce widniałaby okładka poprzedniej wersji.
    # ETAP=1 (domyślnie) robi wszystko poza Pomocą, ETAP=2 wyłącznie Pomoc.
    etap = os.environ.get("ETAP", "1")
    jest_pomoc = lambda x: "-pomoc" in os.path.basename(x["out"])
    shots = [x for x in shots if (jest_pomoc(x) if etap == "2" else not jest_pomoc(x))]

    # TYLKO=<fragment nazwy> — powtórzenie pojedynczych zrzutów bez przechodzenia
    # całej listy od nowa (zrzut czatu potrafi trwać dwie minuty).
    # TYLKO przyjmuje LISTĘ po przecinku (TYLKO=chat,wyszukiwarka) — zmiana wyglądu
    # dotyka zwykle kilku ekranów naraz, a każdy pełny przebieg to kwadrans.
    tylko = os.environ.get("TYLKO")
    if tylko:
        wzorce = [w.strip() for w in tylko.split(",") if w.strip()]
        shots = [x for x in shots
                 if any(w in os.path.basename(x["out"]) for w in wzorce)]
    if not shots:
        return

    cfg = {
        # Profil Edge osobny na język: `--lang` działa przy starcie przeglądarki,
        # a profil przechowuje ustawienia — wspólny profil niósłby język
        # z poprzedniego przebiegu.
        "profile": os.path.join(KATALOG, f".edge-{wdrozenie}-{wydanie}-{jezyk}"),
        "origin": cfgw["origin"],
        "jezyk": jezyk,
        "token": s["token"],
        "user": s["user"],
        "width": 1600,
        "height": 1000,
        "shots": shots,
    }
    sciezka = os.path.join(KATALOG, f".shots-{wdrozenie}-{wydanie}-{jezyk}.json")
    with open(sciezka, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)

    print(f"\n=== {wdrozenie} / {wydanie} / {jezyk} — {len(shots)} zrzutów, {cfgw['origin']} ===")
    subprocess.run([sys.executable, os.path.join(KATALOG, "shot.py"), sciezka], check=True)
    os.remove(sciezka)


def main():
    """python zrzuty_config.py [zco|hirs] [admin|user] [pl|en|cs|de|es|uk]"""
    wdrozenia = [sys.argv[1]] if len(sys.argv) > 1 else list(WDROZENIA)
    wydania = [sys.argv[2]] if len(sys.argv) > 2 else ["admin", "user"]
    jezyki = [sys.argv[3]] if len(sys.argv) > 3 else JEZYKI
    for w in wdrozenia:
        for wyd in wydania:
            for j in jezyki:
                przebieg(w, wyd, j)


if __name__ == "__main__":
    main()
