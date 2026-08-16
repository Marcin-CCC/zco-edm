"""Testy dopuszczalnych typów pól w schematach dokumentów.

Uruchom: pytest backend/tests/test_doc_schemas_typy.py -v

Lista typów jest umową między trzema miejscami naraz: formularzem schematu,
promptem ekstrakcji i eksportem do Excela. Test pilnuje, żeby rozjazd w tej
umowie wyszedł tutaj, a nie u użytkownika przy zapisie schematu.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.doc_schemas.router import _validate_fields


def pole(typ: str):
    return SimpleNamespace(name="kwota_brutto", type=typ)


@pytest.mark.parametrize("typ", ["string", "number", "money", "date", "enum:PLN,EUR"])
def test_typy_dozwolone(typ):
    _validate_fields([pole(typ)])


@pytest.mark.parametrize("typ", ["kwota", "float", "decimal", "", "enum"])
def test_typy_odrzucone(typ):
    with pytest.raises(HTTPException) as e:
        _validate_fields([pole(typ)])
    assert e.value.status_code == 400
    # Komunikat ma wymieniać dozwolone typy — inaczej administrator zgaduje.
    assert "money" in e.value.detail
