"""Planowanie zakresu wyszukiwania dla czatu — jedno miejsce dla wszystkich ścieżek.

Czat ma cztery ścieżki retrievalu i każda inaczej buduje filtr oraz inaczej traktuje
próg trafności:

 1. ZWYKŁA — sam filtr uprawnień, próg 0,50 działa.
 2. WSKAZANE PLIKI — użytkownik sam ustalił zakres, próg wyłączony.
 3. ZAWĘŻENIE LEKSYKALNE — rzadkie słowo z pytania (nazwisko, nazwa własna),
    próg wyłączony, bo wewnątrz wąskiego zbioru trafności są z natury niższe.
 4. RATUNEK PO STRESZCZENIACH — gdy zwykłe fragmenty nie dają kontekstu; zawęża
    do wskazanych dokumentów i wyłącza próg.

Ten moduł powstał po błędzie, który kosztował jedno wdrożenie: dobór z dokumentu
-zwycięzcy zmierzyłem na ścieżce 1, a wadliwe pytanie szło ścieżką 3 — z innym
filtrem i innym zbiorem fragmentów w kontekście. Dopóki plan zakresu żył wewnątrz
funkcji obsługującej żądanie HTTP, nie dało się go odtworzyć w pomiarze inaczej
niż przez przepisanie — czyli przez zgadywanie.

Dzięki wydzieleniu `app/retrieval_bench.py` mierzy DOKŁADNIE to, co robi czat.
Zmiana zachowania w jednym miejscu automatycznie zmienia pomiar.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PlanZakresu:
    """Wszystko, co czat musi wiedzieć o zakresie wyszukiwania jednego pytania."""

    qdrant_filter: dict | None = None
    warunki_rbac: list[dict] = field(default_factory=list)
    wskazane_pliki: list[int] = field(default_factory=list)
    terminy: list[str] = field(default_factory=list)
    wskazane_streszczeniem: list[int] = field(default_factory=list)
    bez_progu: bool = False
    dobrane: list[dict] = field(default_factory=list)
    trafienia: list[dict] = field(default_factory=list)
    w_kontekscie: list[dict] = field(default_factory=list)
    diagnostyka: str = ""

    @property
    def scoped_to_files(self) -> bool:
        """Czy próg trafności w n8n ma być wyłączony."""
        return bool(self.wskazane_pliki or self.terminy or self.bez_progu)


async def zaplanuj_zakres(
    *,
    pytanie: str,
    search_query: str,
    file_ids: list[int] | None,
    folder_filter_enabled: bool,
    allowed_folder_ids: list[int],
    znane_rdzenie: set[str],
) -> PlanZakresu:
    """Zbuduj filtr Qdranta i dobierz fragmenty uzupełniające dla jednego pytania.

    `pytanie` — oryginalna treść (z niej wyciągamy rzadkie słowa),
    `search_query` — pytanie przepisane na samodzielne (idzie do wyszukiwarki).

    Best-effort na każdym kroku: awaria osadzania albo Qdranta oznacza węższy plan,
    nigdy wyjątku — czat ma odpowiedzieć nawet wtedy, gdy usprawnienia nie działają.
    """
    from app.chat.dobor import dobierz_fragmenty
    from app.chat.lexical import terminy_selektywne
    from app.chat.streszczenia import PROG_FRAGMENTU, wskaz_dokumenty
    from app.qdrant_client import count_chunks_with_text, count_points, search_chunks_full
    from app.summaries import wektor as osadz

    plan = PlanZakresu()
    warunki: list[dict] = []
    if folder_filter_enabled:
        warunki.append({"key": "metadata.folder_id", "match": {"any": allowed_folder_ids}})
    # Same uprawnienia, bez zawężeń z treści pytania — dobór szuka właśnie z tym
    # filtrem, bo rzadkie słowo ma wskazać DOKUMENT, a nie ograniczać wybór strony.
    plan.warunki_rbac = list(warunki)

    if file_ids:
        plan.wskazane_pliki = sorted(set(file_ids))
        warunki.append({"key": "metadata.file_id", "match": {"any": plan.wskazane_pliki}})
    else:
        # Zawężenie po nazwie własnej — wyszukiwanie semantyczne nie znajduje nazwisk
        # (zmierzone: właściwe fragmenty 0,28–0,40, niżej niż przypadkowe).
        plan.terminy = terminy_selektywne(
            pytanie, count_chunks_with_text, count_points(), znane_rdzenie
        )
        if plan.terminy:
            warunki.append({"should": [
                {"key": "content", "match": {"text": t}} for t in plan.terminy
            ]})

    # Jedno osadzenie pytania na dwóch odbiorców: streszczenia i dobór.
    wektor_pytania = None
    if not file_ids:
        try:
            wektor_pytania = await osadz(search_query)
        except Exception as e:
            logger.warning(f"[ZAKRES] Osadzenie pytania nieudane: {e}")

    if not file_ids and not plan.terminy:
        plan.wskazane_streszczeniem, plan.bez_progu, plan.diagnostyka = await wskaz_dokumenty(
            search_query,
            {"must": warunki} if warunki else None,
            allowed_folder_ids if folder_filter_enabled else None,
            wektor_pytania=wektor_pytania,
        )
        if plan.wskazane_streszczeniem:
            warunki.append(
                {"key": "metadata.file_id", "match": {"any": plan.wskazane_streszczeniem}}
            )

    plan.qdrant_filter = {"must": warunki} if warunki else None

    # Dobór z dokumentu-zwycięzcy dla pytań o złożonym ciągu rozumowania.
    # Pomijamy, gdy zakres wskazał UŻYTKOWNIK albo gdy nie ma osadzenia.
    if wektor_pytania is not None:
        try:
            plan.trafienia = search_chunks_full(wektor_pytania, plan.qdrant_filter, limit=15)
            # Odwzorowanie węzła „Chunks Filter": przy zawężonym wyszukiwaniu próg
            # jest wyłączony i do kontekstu wchodzi wszystko.
            plan.w_kontekscie = (
                plan.trafienia if (plan.terminy or plan.bez_progu)
                else [t for t in plan.trafienia if t["score"] >= PROG_FRAGMENTU]
            )
            plan.dobrane = await dobierz_fragmenty(
                search_query,
                plan.w_kontekscie,
                {"must": plan.warunki_rbac} if plan.warunki_rbac else None,
                osadz,
                search_chunks_full,
            )
        except Exception as e:      # plan zakresu nie może zablokować odpowiedzi
            logger.warning(f"[ZAKRES] Dobór fragmentów nieudany: {e}")

    return plan
