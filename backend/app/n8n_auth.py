"""
Uwierzytelnianie wywołań WYCHODZĄCYCH z backendu do n8n (kierunek [1]).

UWAGA — nie mylić z `webhook_auth.py`. To są dwa przeciwne kierunki:

    [1]  backend ──POST──► n8n Webhook (trigger)   ← TEN moduł
    [2]  n8n HTTP Request ──PATCH──► backend       ← webhook_auth.py

Kierunek [1] dotyczy triggerów workflowów: uruchomienia parsowania pliku
(`dispatcher.py`) oraz zapytania czatu (`chat/router.py`). Webhooki n8n stoją
pod publiczną domeną, więc bez uwierzytelniania każdy, kto zna URL, może odpalić
workflow — obciążyć GPU Sparka albo wywołać pipeline parsujący.

Domknięcie wymaga OBU połówek naraz:
  1. w n8n: nod Webhook → Authentication → Header Auth → credential,
  2. tutaj: N8N_AUTH_VALUE ustawione na tę samą wartość.

Włączenie samej strony n8n kończy się `403 Authorization data is wrong!`.

Konfiguracja (env):
    N8N_AUTH_HEADER   nazwa nagłówka (domyślnie X-N8N-Webhook-Secret);
                      musi zgadzać się z polem "Header Name" w credentialu n8n
    N8N_AUTH_VALUE    wartość sekretu; puste = nagłówek nie jest wysyłany

Sekret MUSI być inny niż WEBHOOK_SECRET (kierunek [2]). Wspólny sekret dla obu
kierunków oznacza, że wyciek z dowolnej strony otwiera obie.
"""

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_AUTH_HEADER = "X-N8N-Webhook-Secret"


def outgoing_headers() -> dict[str, str]:
    """Nagłówki uwierzytelniające dla żądań backend → n8n.

    Zwraca pusty słownik, gdy N8N_AUTH_VALUE nie jest ustawione — dzięki temu
    włączenie tej ochrony jest wstecznie zgodne i można je wdrożyć etapowo
    (najpierw backend zaczyna wysyłać nagłówek, potem n8n zaczyna go wymagać).
    """
    value = os.getenv("N8N_AUTH_VALUE")
    if not value:
        return {}
    header = os.getenv("N8N_AUTH_HEADER") or DEFAULT_AUTH_HEADER
    return {header: value}
