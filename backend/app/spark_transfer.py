"""
Transfer plików na Spark DGX przez SSH (tryb developmentu lokalnego).

Gdy aplikacja działa lokalnie (na PC), a n8n na Sparku, n8n nie widzi
lokalnych plików. Ten moduł kopiuje wgrany plik przez SSH do wolumenu
docker `zco-edm-app_shared_docs` na Sparku (ten sam, który montują
kontenery edm-backend i n8n_spark jako /data/shared_docs), dzięki czemu
workflow n8n działa identycznie jak dla aplikacji uruchomionej na Sparku.

Mechanizm: strumień pliku przez ssh → docker exec -i <kontener> sh -c
"mkdir -p <dir> && cat > <plik>". Wymaga klucza SSH bez hasła
(zamontowanego do kontenera backendu) oraz openssh-client w obrazie.

Konfiguracja (env):
    SPARK_SSH_TRANSFER=true          # włącza transfer (tylko dev lokalny!)
    SPARK_SSH_HOST=192.168.1.34
    SPARK_SSH_USER=marcin
    SPARK_SSH_KEY_PATH=/app/ssh/id_ed25519.spark
    SPARK_DOCKER_CONTAINER=edm-backend
    SPARK_SHARED_DIR=/data/shared_docs
"""

import os
import logging
import shlex
import shutil
import stat
import subprocess
import tempfile

logger = logging.getLogger(__name__)

_SECURE_KEY_PATH = "/tmp/.spark_ssh_key"

SPARK_SSH_TRANSFER = os.getenv("SPARK_SSH_TRANSFER", "false").lower() in ("1", "true", "yes")
SPARK_SSH_HOST = os.getenv("SPARK_SSH_HOST", "192.168.1.34")
SPARK_SSH_USER = os.getenv("SPARK_SSH_USER", "marcin")
SPARK_SSH_KEY_PATH = os.getenv("SPARK_SSH_KEY_PATH", "/app/ssh/id_ed25519.spark")
SPARK_DOCKER_CONTAINER = os.getenv("SPARK_DOCKER_CONTAINER", "edm-backend")
SPARK_SHARED_DIR = os.getenv("SPARK_SHARED_DIR", "/data/shared_docs")


def spark_transfer_enabled() -> bool:
    """Czy transfer SSH na Sparka jest włączony."""
    return SPARK_SSH_TRANSFER


def _get_secure_key() -> str:
    """Zwróć ścieżkę klucza z bezpiecznymi uprawnieniami (0600).

    Klucz montowany z Windows ma tryb 777, którego ssh odmawia użycia
    ("UNPROTECTED PRIVATE KEY FILE"). Kopiujemy go do /tmp z chmod 600.
    """
    src = SPARK_SSH_KEY_PATH
    if not os.path.exists(src):
        raise RuntimeError(f"Brak klucza SSH: {src}")
    # Odśwież kopię gdy źródło nowsze
    if (not os.path.exists(_SECURE_KEY_PATH)
            or os.path.getmtime(src) > os.path.getmtime(_SECURE_KEY_PATH)):
        shutil.copyfile(src, _SECURE_KEY_PATH)
        os.chmod(_SECURE_KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    return _SECURE_KEY_PATH


def transfer_to_spark(local_path: str, relative_path: str) -> str:
    """Prześlij lokalny plik na Sparka do współdzielonego wolumenu.

    Args:
        local_path: pełna lokalna ścieżka pliku (już zapisanego na dysku)
        relative_path: ścieżka względna wewnątrz shared_docs,
                       np. "certyfikat.pdf" lub "raporty-biurowe/faktura.pdf"

    Returns:
        Zdalna ścieżka pliku widziana przez n8n, np.
        "/data/shared_docs/certyfikat.pdf"

    Raises:
        RuntimeError: gdy transfer się nie powiódł
    """
    relative_path = relative_path.replace("\\", "/").lstrip("/")
    remote_path = f"{SPARK_SHARED_DIR}/{relative_path}"
    remote_dir = os.path.dirname(remote_path)

    # Polecenie wykonywane na Sparku: zapis strumienia do pliku w kontenerze
    docker_cmd = (
        f"docker exec -i {shlex.quote(SPARK_DOCKER_CONTAINER)} sh -c "
        + shlex.quote(f"mkdir -p {shlex.quote(remote_dir)} && cat > {shlex.quote(remote_path)}")
    )

    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",                 # nigdy nie pytaj o hasło
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-i", _get_secure_key(),
        f"{SPARK_SSH_USER}@{SPARK_SSH_HOST}",
        docker_cmd,
    ]

    logger.info(f"[SPARK-TRANSFER] {local_path} -> {SPARK_SSH_HOST}:{remote_path}")

    try:
        with open(local_path, "rb") as fh:
            result = subprocess.run(
                ssh_cmd,
                stdin=fh,
                capture_output=True,
                timeout=120,
            )
    except FileNotFoundError as e:
        raise RuntimeError(f"Brak klienta ssh w kontenerze backendu: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Timeout transferu SSH na Sparka (120s): {e}") from e

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Transfer SSH nie powiódł się (kod {result.returncode}): {stderr}")

    logger.info(f"[SPARK-TRANSFER] OK: {remote_path}")
    return remote_path


def delete_from_spark(remote_path: str) -> dict:
    """Usuń plik ze Sparka (wolumen shared_docs) — odwrotność transfer_to_spark.

    Wołane TYLKO w trybie deweloperskim (gdy `spark_transfer_enabled()`), bo tylko
    wtedy istnieje druga kopia pliku. W docelowym wdrożeniu aplikacja działa NA
    Sparku, plik jest lokalny i kasuje go zwykłe `os.remove` — tu nic się nie
    uruchamia. Bez tego usunięty w aplikacji plik zostawał na dysku Sparka
    (stąd osierocone pliki).

    Usuwa też katalog pliku, jeśli został pusty (schemat <uuid>/<nazwa>).
    Best-effort: awaria nie może przerwać usuwania pliku — zwraca diagnostykę.
    """
    if not remote_path or not remote_path.startswith(SPARK_SHARED_DIR + "/"):
        return {"ok": False, "reason": "ścieżka spoza shared_docs — pomijam"}

    # `rm -f` + próba usunięcia osieroconego katalogu (rmdir usuwa tylko pusty)
    inner = (
        f"rm -f {shlex.quote(remote_path)} && "
        f"rmdir {shlex.quote(os.path.dirname(remote_path))} 2>/dev/null || true"
    )
    docker_cmd = f"docker exec {shlex.quote(SPARK_DOCKER_CONTAINER)} sh -c " + shlex.quote(inner)
    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-i", _get_secure_key(),
        f"{SPARK_SSH_USER}@{SPARK_SSH_HOST}",
        docker_cmd,
    ]
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, timeout=60)
    except Exception as e:
        logger.warning(f"[SPARK-DELETE] {remote_path}: {e}")
        return {"ok": False, "error": str(e)}

    if result.returncode == 0:
        logger.info(f"[SPARK-DELETE] Usunięto {SPARK_SSH_HOST}:{remote_path}")
        return {"ok": True}
    err = result.stderr.decode(errors="replace")[:200]
    logger.warning(f"[SPARK-DELETE] {remote_path}: rc={result.returncode} {err}")
    return {"ok": False, "status": result.returncode, "detail": err}


def fetch_from_spark(remote_path: str, local_path: str) -> None:
    """Pobierz plik ze Sparka (wolumen shared_docs) na lokalny dysk.

    Odwrotność transfer_to_spark: ssh → docker exec cat <plik> → lokalny zapis.
    Używane jako fallback przy pobieraniu/podglądzie, gdy lokalna kopia
    nie istnieje (np. po rebuild kontenera lub plik wgrany z innej instancji).
    """
    docker_cmd = (
        f"docker exec {shlex.quote(SPARK_DOCKER_CONTAINER)} cat {shlex.quote(remote_path)}"
    )
    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-i", _get_secure_key(),
        f"{SPARK_SSH_USER}@{SPARK_SSH_HOST}",
        docker_cmd,
    ]

    logger.info(f"[SPARK-FETCH] {SPARK_SSH_HOST}:{remote_path} -> {local_path}")
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

    # Zapis przez plik tymczasowy — bez półzapisanych plików przy błędzie
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(local_path) or ".")
    try:
        with os.fdopen(fd, "wb") as out:
            result = subprocess.run(ssh_cmd, stdout=out, stderr=subprocess.PIPE, timeout=120)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"Pobranie ze Sparka nie powiodło się (kod {result.returncode}): {stderr}")
        if os.path.getsize(tmp_path) == 0:
            raise RuntimeError("Pobrany plik jest pusty")
        os.replace(tmp_path, local_path)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Timeout pobierania ze Sparka (120s): {e}") from e
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    logger.info(f"[SPARK-FETCH] OK: {local_path} ({os.path.getsize(local_path)} B)")
