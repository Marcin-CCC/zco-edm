"""Poprawki tłumaczeń interfejsu nanoszone przez administratora.

Celowo BEZ `from ... import router`: taki zapis podstawia obiekt `APIRouter` pod
nazwę `app.translations.router` i podmoduł przestaje być osiągalny przez
`import app.translations.router as modul` (potrzebne testom do podstawień).
Wpięcie w `main.py` idzie wprost z podmodułu.
"""
