"""
REST API systemu zarządzania flotą pojazdów.

Udostępnia dane z bazy PostgreSQL jako JSON. Endpointy są opisane w README.md
(sekcja "Kontrakt"), a dokumentacja Swagger jest pod http://localhost:8000/docs.

Uruchomienie lokalne (z folderu api/):
    .venv\\Scripts\\python -m uvicorn main:app --reload
"""

import os
from datetime import datetime
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

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

    Po wyjściu z bloku "with get_conn() as conn:" psycopg sam zatwierdza zmiany
    (COMMIT) i zamyka połączenie, a przy błędzie wycofuje zmiany (ROLLBACK).
    """
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        row_factory=dict_row,
    )


# --- Modele danych (Pydantic) ---------------------------------------------
# Model opisuje, jak wygląda JSON. FastAPI używa modeli do dwóch rzeczy:
# 1) sprawdza dane od klienta: złe dane = automatycznie kod 422 z opisem błędu,
# 2) opisuje odpowiedzi w Swaggerze (pole "Example Value" / "Schema").

# Dozwolone wartości statusu - takie same jak CHECK w db/init.sql.
Status = Literal["active", "inactive", "maintenance"]


class VehicleIn(BaseModel):
    """Dane pojazdu wysyłane przez klienta (POST i PUT). Bez id - nadaje je baza."""
    # Limity długości są takie same jak w VARCHAR(...) w db/init.sql.
    plate: str = Field(min_length=1, max_length=16, examples=["WX 10006"])
    name: str = Field(min_length=1, max_length=64, examples=["Dostawczy F"])
    model: str | None = Field(default=None, max_length=64, examples=["Iveco Daily"])
    status: Status = "active"  # jeśli klient nie poda statusu, przyjmujemy "active"


class Vehicle(VehicleIn):
    """Pojazd zwracany przez API: to samo co VehicleIn plus numer z bazy."""
    id: int


class Position(BaseModel):
    """Jedna pozycja GPS pojazdu."""
    vehicle_id: int
    ts: datetime
    lat: float
    lon: float
    speed_kmh: float | None
    heading: float | None


# --- Funkcje pomocnicze ---------------------------------------------------
VEHICLE_COLUMNS = "id, plate, name, model, status"


def not_found(vehicle_id):
    """Błąd 404 - zwracamy go, gdy pojazdu o podanym numerze nie ma w bazie."""
    return HTTPException(status_code=404, detail=f"Pojazd {vehicle_id} nie istnieje")


def plate_taken(plate):
    """Błąd 409 (konflikt) - tablica rejestracyjna musi być unikalna (UNIQUE w bazie)."""
    return HTTPException(status_code=409, detail=f"Pojazd z tablicą {plate} już istnieje")


# --- Endpointy ------------------------------------------------------------
# Dekorator @app.get("/adres") mówi: "gdy przyjdzie zapytanie GET na ten adres,
# wywołaj funkcję poniżej". response_model mówi FastAPI, jak wygląda odpowiedź.
# Fragment {vehicle_id} w adresie trafia do funkcji jako argument o tej nazwie.
# Uwaga: w SQL zawsze używamy %s zamiast wklejać wartości do tekstu zapytania.
# psycopg sam bezpiecznie wstawia wartości (ochrona przed SQL injection).

@app.get("/health")
def health():
    """Prosty test, czy API w ogóle działa (nie dotyka bazy)."""
    return {"status": "ok"}


@app.get("/vehicles", response_model=list[Vehicle])
def list_vehicles():
    """Lista wszystkich pojazdów floty."""
    with get_conn() as conn:
        rows = conn.execute(f"SELECT {VEHICLE_COLUMNS} FROM vehicles ORDER BY id").fetchall()
    return rows


@app.post("/vehicles", response_model=Vehicle, status_code=201)
def create_vehicle(vehicle: VehicleIn):
    """Dodaje nowy pojazd. Zwraca go razem z numerem nadanym przez bazę (kod 201)."""
    try:
        with get_conn() as conn:
            # RETURNING zwraca wstawiony wiersz, więc znamy id nadane przez bazę.
            row = conn.execute(
                f"INSERT INTO vehicles (plate, name, model, status) "
                f"VALUES (%s, %s, %s, %s) RETURNING {VEHICLE_COLUMNS}",
                (vehicle.plate, vehicle.name, vehicle.model, vehicle.status),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise plate_taken(vehicle.plate)
    return row


@app.get("/vehicles/{vehicle_id}", response_model=Vehicle)
def get_vehicle(vehicle_id: int):
    """Jeden pojazd o podanym numerze."""
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {VEHICLE_COLUMNS} FROM vehicles WHERE id = %s", (vehicle_id,)
        ).fetchone()
    if row is None:  # fetchone() zwraca None, gdy zapytanie nic nie znalazło
        raise not_found(vehicle_id)
    return row


@app.put("/vehicles/{vehicle_id}", response_model=Vehicle)
def update_vehicle(vehicle_id: int, vehicle: VehicleIn):
    """Zmienia dane pojazdu. Trzeba podać wszystkie pola (tak działa PUT)."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                f"UPDATE vehicles SET plate = %s, name = %s, model = %s, status = %s "
                f"WHERE id = %s RETURNING {VEHICLE_COLUMNS}",
                (vehicle.plate, vehicle.name, vehicle.model, vehicle.status, vehicle_id),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise plate_taken(vehicle.plate)
    if row is None:  # UPDATE nie znalazł wiersza o tym id
        raise not_found(vehicle_id)
    return row


@app.delete("/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int):
    """Usuwa pojazd. Jego pozycje znikają razem z nim (ON DELETE CASCADE w bazie)."""
    with get_conn() as conn:
        deleted = conn.execute("DELETE FROM vehicles WHERE id = %s", (vehicle_id,)).rowcount
    if deleted == 0:  # rowcount = liczba usuniętych wierszy
        raise not_found(vehicle_id)
    # 204 No Content = "udało się, ale nie ma nic do odesłania".
    return Response(status_code=204)


@app.get("/positions/latest", response_model=list[Position])
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


@app.get("/vehicles/{vehicle_id}/history", response_model=list[Position])
def vehicle_history(
    vehicle_id: int,
    # "from" to słowo zarezerwowane w Pythonie, więc zmienna nazywa się from_,
    # a alias="from" sprawia, że w adresie nadal piszemy ?from=...
    from_: datetime | None = Query(default=None, alias="from",
                                   description="Początek zakresu, np. 2026-11-24T10:00:00Z"),
    to: datetime | None = Query(default=None,
                                description="Koniec zakresu, np. 2026-11-24T11:00:00Z"),
):
    """Historia pozycji pojazdu, od najstarszej do najnowszej (gotowa do narysowania trasy).

    Parametry from i to są opcjonalne. Bez nich zwracamy całą historię.
    """
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(status_code=422, detail="Parametr 'from' musi być wcześniejszy niż 'to'")

    with get_conn() as conn:
        # Najpierw sprawdzamy, czy pojazd istnieje, żeby odróżnić
        # "brak pojazdu" (404) od "pojazd jest, ale nie ma pozycji" (pusta lista).
        if conn.execute("SELECT 1 FROM vehicles WHERE id = %s", (vehicle_id,)).fetchone() is None:
            raise not_found(vehicle_id)

        # Sztuczka: "%s IS NULL OR ts >= %s" - jeśli parametru nie podano (None),
        # warunek jest zawsze prawdziwy, czyli w praktyce nie filtrujemy.
        rows = conn.execute(
            """
            SELECT vehicle_id, ts, lat, lon, speed_kmh, heading
            FROM positions
            WHERE vehicle_id = %s
              AND (%s::timestamptz IS NULL OR ts >= %s)
              AND (%s::timestamptz IS NULL OR ts <= %s)
            ORDER BY ts
            """,
            (vehicle_id, from_, from_, to, to),
        ).fetchall()
    return rows
