# Pakiet celowo NIE re-eksportuje routera. `app/auth/auth.py` importuje
# `app.roles.service`, a to wykonałoby ten plik — router importuje
# `get_current_user` z auth, więc powstałby cykl importów.
