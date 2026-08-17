"""Buduje konfiguracje dla shot.py i uruchamia zrzuty dla obu wdrożeń.

Uruchomienie:
    python zrzuty_config.py [zco|hirs] [admin|user]

Bez argumentów robi wszystkie cztery przebiegi. Tokeny sesji generuje po stronie
serwera (kod aplikacji, `hash`/`create_access_token`) — nigdzie nie pojawia się
hasło, a konta nie są zakładane ani modyfikowane na potrzeby zrzutów.

Zrzuty lądują w `zrzuty/<wdrożenie>/`, skąd bierze je `generuj.py`.
"""
import json
import os
import subprocess
import sys

KATALOG = os.path.dirname(os.path.abspath(__file__))
SPARK = "marcin@192.168.1.34"

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
# Folder udostępniony roli konta użytkownika — inny niż powyżej, bo zwykłe
# konto widzi tylko część zbioru.
FOLDER_UZYTKOWNIKA = {"zco": "Praca zdalna", "hirs": "Normy i standardy"}

PYTANIE = {
    "zco": "Od jakiego wieku dziecka przysługuje dofinansowanie do wypoczynku?",
    "hirs": "Jakie normy obowiązują przy przechowywaniu dokumentacji?",
}
PYTANIE_WYSZUKIWARKI = {
    "zco": "wszystkie zarządzenia z 2023 roku",
    "hirs": "wszystkie faktury",
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


def zrzuty_admina(w, katalog):
    """Lista zrzutów wydania administratora. `w` — klucz wdrożenia."""
    p = lambda nazwa: os.path.join(katalog, nazwa)
    folder = FOLDER_ROBOCZY[w]
    return [
        {"path": "/login", "out": p("a00-logowanie.png"), "wyloguj": True, "wait": 3},
        {"path": "/dashboard", "out": p("a01-pulpit.png"), "wait": 6},
        {"path": "/dashboard", "out": p("a19-panele.png"), "wait": 6,
         "js": "[...document.querySelectorAll('h3')].find(h=>h.textContent.includes('Szybkie akcje'))"
               "?.scrollIntoView({block:'center'})",
         "clip_js": "[...document.querySelectorAll('h3')]"
                    ".find(h=>h.textContent.includes('Szybkie akcje'))?.closest('div.grid')", "pad": 10},
        {"path": "/dashboard/files", "out": p("a02-pliki.png"), "wait": 5},
        {"path": "/dashboard/files", "out": p("a02b-kafelki.png"), "wait": 5,
         "js": "[...document.querySelectorAll('[aria-label=\"Widok listy plików\"] button')]"
               ".find(b=>b.textContent.includes('Kafelki'))?.click()", "wait_js": 1.5},
        {"path": "/dashboard/files", "out": p("a03-wysylka.png"), "wait": 5,
         "js": js_klik("Prześlij pliki"), "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a04-uprawnienia.png"), "wait": 5,
         "js": js_tytul("Uprawnienia folderu"), "wait_js": 2.0, "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a05-zmiana-nazwy.png"), "wait": 5,
         "js": js_tytul("Zmień nazwę folderu"), "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a07-szczegoly.png"), "wait": 5,
         "js": js_wejdz_do_folderu(folder), "wait_js": 3.5,
         "js2": "document.querySelector('tbody tr')?.click()", "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a06-przenoszenie.png"), "wait": 5,
         "js": js_wejdz_do_folderu(folder), "wait_js": 3.5,
         "js2": js_tytul("Przenieś do innego folderu"), "clip": OKNO},
        {"path": "/dashboard/files", "out": p("a20-nazwy.png"), "wait": 5,
         "js": js_wejdz_do_folderu(folder), "wait_js": 3.5,
         "js2": "[...document.querySelectorAll('tbody input[type=checkbox]')].slice(0,4)"
                ".forEach(c=>c.click());"
                "[...document.querySelectorAll('button')]"
                ".find(b=>b.textContent.includes('Wykonaj akcję'))?.click();",
         "js3": "[...document.querySelectorAll('button')]"
                ".find(b=>b.textContent.includes('Nadaj nazwy'))?.click()",
         "wait_js3": 4.0, "clip": OKNO},
        {"path": "/dashboard/chat", "out": p("a08-chat.png"), "wait": 5,
         "js": js_wpisz("textarea", PYTANIE[w]) + ";" + js_klik("Wyślij"), "wait_js": 95,
         "js2": "(() => { const o=[...document.querySelectorAll('div')]"
               ".find(d=>d.className.includes('overflow-y-auto') "
               "&& d.className.includes('space-y-4'));"
               " if(o) o.scrollTop=o.scrollHeight; })()", "wait_js2": 2.0,
         },
        {"path": "/dashboard/wyszukiwanie", "out": p("a09-wyszukiwarka.png"), "wait": 4,
         "js": js_wpisz("input[placeholder^='np.']", PYTANIE_WYSZUKIWARKI[w]) + ";" + js_klik("Zapytaj"),
         "wait_js": 12},
        {"path": "/dashboard/users", "out": p("a10-uzytkownicy.png"), "wait": 4},
        {"path": "/dashboard/access-list", "out": p("a11-lista-dostepow.png"), "wait": 4},
        {"path": "/dashboard/access-list", "out": p("a11b-rola.png"), "wait": 4,
         "js": js_klik("Dodaj rolę"), "clip": OKNO},
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


def zrzuty_uzytkownika(w, katalog):
    p = lambda nazwa: os.path.join(katalog, nazwa)
    return [
        {"path": "/login", "out": p("u00-logowanie.png"), "wyloguj": True, "wait": 3},
        {"path": "/dashboard", "out": p("u01-pulpit.png"), "wait": 6},
        {"path": "/dashboard/files", "out": p("u02-pliki.png"), "wait": 5},
        {"path": "/dashboard/files", "out": p("u02b-folder.png"), "wait": 5,
         "js": js_wejdz_do_folderu(FOLDER_UZYTKOWNIKA[w]), "wait_js": 3.5},
        {"path": "/dashboard/chat", "out": p("u03-chat.png"), "wait": 5,
         "js": js_wpisz("textarea", PYTANIE[w]) + ";" + js_klik("Wyślij"), "wait_js": 95,
         "js2": "(() => { const o=[...document.querySelectorAll('div')]"
               ".find(d=>d.className.includes('overflow-y-auto') "
               "&& d.className.includes('space-y-4'));"
               " if(o) o.scrollTop=o.scrollHeight; })()", "wait_js2": 2.0,
         },
        {"path": "/dashboard/wyszukiwanie", "out": p("u04-wyszukiwarka.png"), "wait": 4,
         "js": js_wpisz("input[placeholder^='np.']", PYTANIE_WYSZUKIWARKI[w]) + ";" + js_klik("Zapytaj"),
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


def przebieg(wdrozenie, wydanie):
    cfgw = WDROZENIA[wdrozenie]
    katalog = os.path.join(KATALOG, "zrzuty", wdrozenie)
    os.makedirs(katalog, exist_ok=True)
    s = sesja(wdrozenie, cfgw["konta"][wydanie])
    shots = (zrzuty_admina if wydanie == "admin" else zrzuty_uzytkownika)(wdrozenie, katalog)

    # Ekran Pomoc pokazuje instrukcję, więc jego zrzut ma sens dopiero PO wdrożeniu
    # nowego wydania — inaczej w ramce widniałaby okładka poprzedniej wersji.
    # ETAP=1 (domyślnie) robi wszystko poza Pomocą, ETAP=2 wyłącznie Pomoc.
    etap = os.environ.get("ETAP", "1")
    jest_pomoc = lambda x: "-pomoc" in os.path.basename(x["out"])
    shots = [x for x in shots if (jest_pomoc(x) if etap == "2" else not jest_pomoc(x))]

    # TYLKO=<fragment nazwy> — powtórzenie pojedynczych zrzutów bez przechodzenia
    # całej listy od nowa (zrzut czatu potrafi trwać dwie minuty).
    tylko = os.environ.get("TYLKO")
    if tylko:
        shots = [x for x in shots if tylko in os.path.basename(x["out"])]
    if not shots:
        return

    cfg = {
        "profile": os.path.join(KATALOG, f".edge-{wdrozenie}-{wydanie}"),
        "origin": cfgw["origin"],
        "token": s["token"],
        "user": s["user"],
        "width": 1600,
        "height": 1000,
        "shots": shots,
    }
    sciezka = os.path.join(KATALOG, f".shots-{wdrozenie}-{wydanie}.json")
    with open(sciezka, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)

    print(f"\n=== {wdrozenie} / {wydanie} — {len(shots)} zrzutów, {cfgw['origin']} ===")
    subprocess.run([sys.executable, os.path.join(KATALOG, "shot.py"), sciezka], check=True)
    os.remove(sciezka)


def main():
    wdrozenia = [sys.argv[1]] if len(sys.argv) > 1 else list(WDROZENIA)
    wydania = [sys.argv[2]] if len(sys.argv) > 2 else ["admin", "user"]
    for w in wdrozenia:
        for wyd in wydania:
            przebieg(w, wyd)


if __name__ == "__main__":
    main()
