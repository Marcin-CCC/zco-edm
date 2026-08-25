"""Testy licznika plików na kafelku folderu (ekran Pliki).

Uruchom: pytest backend/tests/test_folders_licznik.py -v

Licznik pokazuje sumę Z PODFOLDERAMI, na dowolną głębokość. Wcześniej liczył tylko
pliki leżące bezpośrednio w folderze, więc folder-katalog (same podfoldery w środku)
pokazywał „0 plików", mimo że w jego gałęzi leżało kilkadziesiąt dokumentów —
i zniechęcał do wejścia głębiej.

Sumujemy po zbudowanym drzewie, a ono jest już zawężone do folderów czytelnych dla
użytkownika. Ten test pilnuje obu rzeczy: arytmetyki i tego, że suma nie przecieka
przez granicę uprawnień.
"""
from app.folders.router import build_folder_tree


class _Folder:
    """Minimalny odpowiednik wiersza z bazy — `build_folder_tree` czyta tylko atrybuty."""

    def __init__(self, id, name, parent_id=None):
        self.id = id
        self.name = name
        self.parent_id = parent_id
        self.path = f"/{name}"
        self.description = None
        self.created_by = 1
        self.created_at = None
        self.updated_at = None


def drzewo(foldery, liczby, allowed_ids=None):
    """Odwzorowanie tego, co robi endpoint `/folders/tree`.

    Zawężenie listy folderów do widocznych NIE dzieje się w `build_folder_tree` —
    robi to wołający, a `allowed_ids` służy tam już tylko do przeniesienia folderu
    o niedostępnym rodzicu na najwyższy poziom. Test musi wołać tak samo, inaczej
    sprawdzałby układ, który w aplikacji nie występuje.
    """
    widoczne = foldery if allowed_ids is None else [f for f in foldery if f.id in allowed_ids]
    return build_folder_tree(widoczne, file_counts=liczby, allowed_ids=allowed_ids)


def znajdz(galezie, nazwa):
    for g in galezie:
        if g.name == nazwa:
            return g
        gl = znajdz(g.children, nazwa)
        if gl:
            return gl
    return None


# Dostawcy ─ Aspironix ─ Opatrunki
#          └ Schulke
FOLDERY = [
    _Folder(1, "Dostawcy"),
    _Folder(2, "Aspironix", parent_id=1),
    _Folder(3, "Opatrunki", parent_id=2),
    _Folder(4, "Schulke", parent_id=1),
]


class TestSumowania:
    def test_folder_bez_podfolderow_liczy_swoje(self):
        t = drzewo(FOLDERY, {3: 7})
        assert znajdz(t, "Opatrunki").file_count == 7

    def test_suma_schodzi_na_dowolna_glebokosc(self):
        """Dostawcy nie mają ani jednego własnego pliku, a mają 7 + 5 w gałęzi."""
        t = drzewo(FOLDERY, {3: 7, 4: 5})
        assert znajdz(t, "Aspironix").file_count == 7
        assert znajdz(t, "Dostawcy").file_count == 12

    def test_wlasne_pliki_doliczane_do_podfolderow(self):
        t = drzewo(FOLDERY, {1: 2, 2: 3, 3: 7, 4: 5})
        assert znajdz(t, "Aspironix").file_count == 10      # 3 własne + 7 z Opatrunków
        assert znajdz(t, "Dostawcy").file_count == 17       # 2 + 10 + 5

    def test_liczba_wlasnych_zostaje_osobno(self):
        """Potrzebna do wyjaśnienia różnicy, gdy wszystko siedzi w podfolderach."""
        g = znajdz(drzewo(FOLDERY, {1: 2, 3: 7}), "Dostawcy")
        assert (g.file_count, g.direct_file_count) == (9, 2)

    def test_pusta_galaz_to_zero_a_nie_blad(self):
        assert znajdz(drzewo(FOLDERY, {}), "Dostawcy").file_count == 0


class TestUprawnien:
    def test_suma_nie_przecieka_przez_granice_dostepu(self):
        """Użytkownik widzi „Dostawcy" i „Schulke", ale nie gałąź Aspironiksu.
        Licznik na „Dostawcach" NIE MOŻE zdradzać, ile tam leży dokumentów."""
        widoczne = {1, 4}
        t = drzewo(FOLDERY, {2: 3, 3: 7, 4: 5}, allowed_ids=widoczne)
        assert znajdz(t, "Dostawcy").file_count == 5
        assert znajdz(t, "Aspironix") is None

    def test_folder_z_niewidocznym_rodzicem_idzie_na_gore_z_wlasna_suma(self):
        """Gdy rodzic jest niedostępny, podfolder wypływa na najwyższy poziom —
        razem ze swoją gałęzią, ale bez doliczania go do tamtego rodzica."""
        widoczne = {2, 3}
        t = drzewo(FOLDERY, {2: 3, 3: 7}, allowed_ids=widoczne)
        assert [g.name for g in t] == ["Aspironix"]
        assert t[0].file_count == 10
