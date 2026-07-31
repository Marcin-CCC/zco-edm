# Schemat środowiska pracy i wdrożenia

Graf połączeń komponentów deweloperskich i serwerowych, z podziałem na komputer lokalny
i Spark DGX.

- `ZCO-DM-srodowisko.html` — do oglądania (rysunek + omówienie pod spodem),
- `ZCO-DM-srodowisko.pdf` — A3 poziomo, rysunek na pierwszej stronie, opis na drugiej,
- `ZCO-DM-srodowisko.svg` — sam rysunek, do wklejenia w dokumentację lub prezentację.

```bash
python generuj.py
```

Pliki: `stale.py` (kolory i klocki: ramka, strefa, strzałka), `uklad.py` (rozmieszczenie
i trasowanie), `generuj.py` (HTML, SVG, PDF + opis).

## Skąd biorą się dane na rysunku

Nie z pamięci — z działającego środowiska:

| Element schematu | Źródło |
|---|---|
| kontenery, porty | `docker ps` na obu maszynach |
| adresy usług dla backendu | zmienne środowiskowe kontenerów, `backend/.env.dev` |
| mostki trybu deweloperskiego | `docker-compose.dev.yaml` (`BACKEND_CALLBACK_URL`, `SPARK_SSH_*`) |
| przepływy w n8n i wołane usługi | definicje obu workflow odczytane z API n8n |
| nazwy kolekcji i modeli | `GET /collections` w Qdrancie, `/api/tags` w Ollamie, `/v1/models` w vLLM |
| wdrożenie | `.github/workflows/*.yml`, `systemctl` na Sparku |

Po zmianie środowiska warto powtórzyć te odczyty i poprawić `uklad.py` — rysunek jest tylko
tak aktualny, jak dzień, w którym powstał (data w nagłówku).

## Zasada trasowania

Slajd łatwo zamienić w plątaninę linii. Trzymamy się trzech korytarzy:

- pionowy między strefami (x ≈ 500–536) — połączenia trybu deweloperskiego,
- poziomy nad strefami (y ≈ 218) — połączenie do bazy danych,
- dwie poziome szyny wewnątrz Sparka (y = 558 i y = 716) — n8n do usług i modeli.

Żadna linia nie przechodzi przez kafelek. Po zmianach warto wyrenderować rysunek do PNG
i obejrzeć: nakładające się etykiety widać wyłącznie na obrazku, nie w kodzie.
