"""
REST API systemu zarządzania flotą pojazdów.

Udostępnia dane z bazy PostgreSQL jako JSON. Endpointy są opisane w README.md
(sekcja "Kontrakt"), a dokumentacja Swagger jest pod http://localhost:8000/docs.

Uruchomienie lokalne (z folderu api/):
    .venv\\Scripts\\python -m uvicorn main:app --reload
"""

import os

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI

# --- Konfiguracja ---------------------------------------------------------
# Dane do połączenia z bazą bierzemy ze zmiennych środowiskowych.
# W Dockerze DB_HOST to "postgres" (nazwa usługi z docker-compose),
# a uruchamiając API na własnym komputerze używamy wartości domyślnych
# (takich samych jak w docker-compose.yml).
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "fleet")
DB_USER = os.getenv("POSTGRES_USER", "fleet")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "fleet_dev_pass")

# Obiekt aplikacji. Tytuł pojawi się na górze strony Swaggera.
app = FastAPI(title="Fleet API", description="System zarządzania flotą pojazdów")


def get_conn():
    """Otwiera nowe połączenie z bazą.

    Nowe połączenie przy każdym zapytaniu jest wolniejsze niż pula połączeń,
    ale najprostsze do zrozumienia i w naszym projekcie w zupełności wystarczy.
    dict_row sprawia, że każdy wiersz przychodzi jako słownik, np.
    {"id": 1, "plate": "WX 10001", ...}, a FastAPI sam zamienia słowniki na JSON.
    """
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        row_factory=dict_row,
    )


# --- Endpointy ------------------------------------------------------------
# Dekorator @app.get("/adres") mówi: "gdy przyjdzie zapytanie GET na ten adres,
# wywołaj funkcję poniżej". To, co funkcja zwróci, trafi do klienta jako JSON
# z kodem 200 OK.

@app.get("/health")
def health():
    """Prosty test, czy API w ogóle działa (nie dotyka bazy)."""
    return {"status": "ok"}


@app.get("/vehicles")
def list_vehicles():
    """Lista wszystkich pojazdów floty."""
    # "with" zamyka połączenie po wyjściu z bloku, nawet jeśli wystąpi błąd.
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, plate, name, model, status FROM vehicles ORDER BY id"
        ).fetchall()
    return rows


@app.get("/positions/latest")
def latest_positions():
    """Ostatnia znana pozycja każdego pojazdu (z niej korzysta mapa).

    DISTINCT ON (vehicle_id) bierze z każdej grupy (jednego pojazdu) tylko
    pierwszy wiersz, a ORDER BY ... ts DESC ustawia najnowszy wiersz na początku.
    Pojazdy, które nie wysłały jeszcze żadnej pozycji, nie pojawią się w wyniku.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (vehicle_id)
                   vehicle_id, ts, lat, lon, speed_kmh, heading
            FROM positions
            ORDER BY vehicle_id, ts DESC
            """
        ).fetchall()
    return rows
