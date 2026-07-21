"""
Uwierzytelnianie wywołań przychodzących od n8n (shared secret).

Endpointy /api/webhook/* oraz POST /api/chat/sources są wołane przez workflow
n8n, więc nie mogą wymagać tokenu JWT użytkownika. Zabezpiecza je wspólny
sekret przesyłany w nagłówku X-Webhook-Secret.

Tryb działania zależy od zmiennej środowiskowej WEBHOOK_SECRET:

- NIEUSTAWIONA — żądania przechodzą bez weryfikacji, ale każde jest logowane
  ostrzeżeniem. Tryb przejściowy: pozwala wdrożyć backend zanim workflowy n8n
  zostaną uzupełnione o nagłówek, bez zrywania działającego pipeline'u.
- USTAWIONA — nagłówek jest wymagany i musi się zgadzać, inaczej 401.

Docelowo sekret MUSI być ustawiony na produkcji: bez niego dowolny host,
który dosięgnie backendu, może zmienić status dowolnego pliku albo podstawić
źródła odpowiedzi czatu.

Konfiguracja po stronie n8n: w nodach HTTP Request wywołujących backend
(„Status PROCESSING sending", „Status READY sending", „Sources") dodać
nagłówek X-Webhook-Secret o tej samej wartości.
"""

import hmac
import logging
import os

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

WEBHOOK_SECRET_HEADER = "X-Webhook-Secret"


def _get_secret() -> str | None:
    """Sekret z env; pusty string traktujemy jak brak konfiguracji."""
    return os.getenv("WEBHOOK_SECRET") or None


async def verify_webhook_secret(
    x_webhook_secret: str | None = Header(default=None, alias=WEBHOOK_SECRET_HEADER),
) -> None:
    """Zależność FastAPI chroniąca endpointy wywoływane przez n8n."""
    expected = _get_secret()

    if expected is None:
        if x_webhook_secret:
            # Sygnał dla wdrożenia etapowego: n8n już wysyła nagłówek, więc
            # ustawienie WEBHOOK_SECRET nie zerwie callbacków.
            logger.warning(
                "[WEBHOOK-AUTH] Nagłówek %s OBECNY, ale WEBHOOK_SECRET nie jest "
                "ustawiony — n8n jest gotowy, można włączyć egzekwowanie.",
                WEBHOOK_SECRET_HEADER,
            )
        else:
            logger.warning(
                "[WEBHOOK-AUTH] WEBHOOK_SECRET nie jest ustawiony i nie przesłano "
                "nagłówka %s — żądanie przyjęte BEZ weryfikacji.",
                WEBHOOK_SECRET_HEADER,
            )
        return

    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
        logger.warning(
            "[WEBHOOK-AUTH] Odrzucono żądanie: nagłówek %s %s.",
            WEBHOOK_SECRET_HEADER,
            "nie pasuje" if x_webhook_secret else "nie został przesłany",
        )
        raise HTTPException(status_code=401, detail="Nieprawidłowy sekret webhooka.")
