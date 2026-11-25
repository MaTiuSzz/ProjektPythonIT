"""
Testy funkcji parse_message z ingestor.py (nie potrzebują Dockera ani bazy).

Uruchomienie z głównego folderu projektu:
    py -m pip install pytest
    py -m pytest ingestor
"""

import json
from datetime import datetime

import pytest

import ingestor

# Poprawna wiadomość, taka jak wysyła symulator (format z README, sekcja "Kontrakt").
GOOD = {
    "vehicle_id": 1,
    "ts": "2026-11-24T10:00:00Z",
    "lat": 52.2301,
    "lon": 21.0130,
    "speed_kmh": 47.5,
    "heading": 90,
}


def message(**changes):
    """Zwraca poprawną wiadomość (jako tekst JSON) z podmienionymi polami."""
    data = dict(GOOD)
    data.update(changes)
    return json.dumps(data)


def test_poprawna_wiadomosc_daje_krotke_do_zapisu():
    row = ingestor.parse_message(message())
    # Kolejność jak w INSERT_SQL: vehicle_id, ts, lat, lon, speed_kmh, heading.
    assert row == (1, datetime(2026, 11, 24, 10, 0, 0), 52.2301, 21.0130, 47.5, 90.0)


def test_wiadomosc_przychodzi_jako_bajty():
    # Biblioteka MQTT podaje treść wiadomości jako bajty, nie jako tekst.
    row = ingestor.parse_message(message().encode("utf-8"))
    assert row[0] == 1


def test_czas_z_inna_strefa_jest_zamieniony_na_utc():
    # 12:00 w strefie +02:00 to 10:00 w UTC.
    row = ingestor.parse_message(message(ts="2026-11-24T12:00:00+02:00"))
    assert row[1] == datetime(2026, 11, 24, 10, 0, 0)


def test_brak_predkosci_i_kierunku_daje_none():
    data = dict(GOOD)
    del data["speed_kmh"]
    del data["heading"]
    row = ingestor.parse_message(json.dumps(data))
    assert row[4] is None
    assert row[5] is None


@pytest.mark.parametrize(
    "payload",
    [
        "to nie jest JSON",
        "",
        '{"vehicle_id": 1, "ts": ',                              # JSON urwany w połowie
        json.dumps({k: v for k, v in GOOD.items() if k != "lat"}),  # brak pola lat
        message(ts="2026-11-24T10:00:00"),                       # czas bez strefy (brak "Z")
        message(ts="wczoraj"),                                   # czas, którego nie da się odczytać
        message(lat=520.2),                                      # szerokość poza zakresem
        message(lon=181),                                        # długość poza zakresem
        message(vehicle_id="abc"),                               # numer auta nie jest liczbą
        message(lat="gdzieś"),                                   # szerokość nie jest liczbą
    ],
)
def test_zepsuta_wiadomosc_rzuca_valueerror(payload):
    with pytest.raises(ValueError):
        ingestor.parse_message(payload)
