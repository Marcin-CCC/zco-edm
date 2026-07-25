"""Sygnał aktywności czatu — priorytet czatu nad parsowaniem.

Czat i parsowanie dzielą JEDEN model (vLLM na Sparku). Gdy trwa czat, dyspozytor
wstrzymuje wysłanie kolejnego pliku do parsowania, żeby model odpowiadał
interaktywnemu użytkownikowi bez czekania w kolejce. Plik będący akurat w trakcie
parsowania i tak dokończy (nie da się go czysto przerwać) — wstrzymujemy tylko
START kolejnego.

Licznik żyje w procesie backendu. W demo czat i callbacki kolejki (a więc i
dispatch) obsługuje ta sama instancja (Spark), więc licznik w procesie wystarcza.
"""
import threading

_lock = threading.Lock()
_active_chats = 0


def chat_started() -> None:
    global _active_chats
    with _lock:
        _active_chats += 1


def chat_finished() -> None:
    global _active_chats
    with _lock:
        _active_chats = max(0, _active_chats - 1)


def is_chat_active() -> bool:
    return _active_chats > 0
