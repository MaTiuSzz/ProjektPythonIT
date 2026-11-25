"""
Ingestor: odbiera pozycje aut z brokera MQTT i zapisuje je do bazy MySQL.

Działa jak urzędnik przy okienku: broker podaje mu kolejne "listy" (wiadomości
z pozycją auta), a on każdą przepisuje jako nowy wiersz do tabeli positions.

Topic i format wiadomości są opisane w README.md (sekcja "Kontrakt").
"""

import json
import os
import time
from datetime import datetime, timezone

import mysql.connector
import paho.mqtt.client as mqtt

# --- Konfiguracja ---------------------------------------------------------
# Wartości można zmienić zmiennymi środowiskowymi, bez ruszania kodu.
# W Dockerze (docker-compose) ustawiamy MQTT_HOST=broker i DB_HOST=mysql.
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = "fleet/vehicles/+/gps"  # "+" znaczy: dowolny numer auta
QOS = 1

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))  # uruchamiając z PyCharma na swoim komputerze: 3307
DB_NAME = os.getenv("MYSQL_DATABASE", "fleet")
DB_USER = os.getenv("MYSQL_USER", "fleet")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "fleet_dev_pass")

# Polecenie SQL zapisujące jedną pozycję. Znaki %s to "puste miejsca", które wypełnimy
# wartościami osobno (nigdy nie sklejamy SQL z tekstu z wiadomości - to niebezpieczne).
INSERT_SQL = (
    "INSERT INTO positions (vehicle_id, ts, lat, lon, speed_kmh, heading) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)

# Kod błędu MySQL: "klucz obcy nie pasuje", czyli w tabeli vehicles nie ma takiego auta.
MYSQL_NO_SUCH_VEHICLE = 1452

# --- Stan programu --------------------------------------------------------
db = None      # połączenie z bazą (ustawiane w main)
saved = 0      # ile pozycji zapisaliśmy od startu


# --- Baza danych ----------------------------------------------------------
def connect_db():
    """Łączy się z bazą. Jeśli baza jeszcze wstaje, ponawia próbę co 3 sekundy."""
    while True:
        try:
            # autocommit=True: każdy zapis od razu trafia na stałe do bazy
            # (bez tego zmiany czekałyby na osobne polecenie commit, jak niezapisany plik).
            return mysql.connector.connect(
                host=DB_HOST, port=DB_PORT, database=DB_NAME,
                user=DB_USER, password=DB_PASSWORD, autocommit=True,
            )
        except mysql.connector.Error as err:
            print(f"Baza niedostępna ({err}). Próbuję ponownie za 3 s...")
            time.sleep(3)


# --- Rozpakowanie wiadomości ----------------------------------------------
def parse_message(payload):
    """Zamienia tekst JSON z brokera na krotkę gotową do zapisu w bazie.

    Jeśli wiadomość jest zepsuta (zły JSON, brak pola, dziwne wartości), rzuca ValueError.
    """
    try:
        data = json.loads(payload)
        vehicle_id = int(data["vehicle_id"])
        lat = float(data["lat"])
        lon = float(data["lon"])
        speed = None if data.get("speed_kmh") is None else float(data["speed_kmh"])
        heading = None if data.get("heading") is None else float(data["heading"])
        ts = datetime.fromisoformat(data["ts"])  # np. "2026-11-24T10:00:00Z"
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
        raise ValueError(f"zła wiadomość ({err!r})") from err

    if ts.tzinfo is None:
        raise ValueError("czas bez strefy (brakuje 'Z' na końcu)")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"współrzędne poza zakresem ({lat}, {lon})")

    # Kolumna DATETIME w MySQL nie przechowuje strefy czasowej, więc zapisujemy czas
    # w UTC i odcinamy informację o strefie (tak umówiliśmy się w README).
    ts_utc = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return (vehicle_id, ts_utc, lat, lon, speed, heading)


# --- MQTT: funkcje wywoływane przez bibliotekę ----------------------------
def on_connect(client, userdata, flags, reason_code, properties):
    """Biblioteka wywołuje ją po połączeniu z brokerem (także po ponownym połączeniu).

    Subskrypcję robimy tutaj, a nie raz w main, bo po zerwaniu połączenia
    broker o niej zapomina i trzeba ją zgłosić od nowa.
    """
    print(f"Połączono z brokerem {MQTT_HOST}:{MQTT_PORT} (kod: {reason_code})")
    client.subscribe(TOPIC, qos=QOS)
    print(f"Słucham kanału {TOPIC}")


def on_message(client, userdata, msg):
    """Biblioteka wywołuje ją przy KAŻDEJ wiadomości, która przyjdzie z brokera."""
    global saved

    # 1. Rozpakuj wiadomość. Zepsutą pomijamy, żeby jedna zła nie zatrzymała całego programu.
    try:
        row = parse_message(msg.payload)
    except ValueError as err:
        print(f"Pomijam wiadomość z kanału {msg.topic}: {err}")
        return

    # 2. Zapisz do bazy.
    try:
        db.ping(reconnect=True, attempts=3, delay=1)  # jeśli połączenie z bazą padło, odnów je
        cursor = db.cursor()
        cursor.execute(INSERT_SQL, row)
        cursor.close()
    except mysql.connector.Error as err:
        if err.errno == MYSQL_NO_SUCH_VEHICLE:
            print(f"Pomijam: auto o numerze {row[0]} nie istnieje w tabeli vehicles")
        else:
            print(f"Błąd zapisu do bazy: {err}")
        return

    # 3. Co 10 zapisów wypisz podsumowanie, żeby logi nie były zalane (5 aut x 1 wiadomość/s).
    saved += 1
    if saved % 10 == 0:
        print(f"[{time.strftime('%H:%M:%S')}] zapisano {saved} pozycji "
              f"(ostatnia: auto {row[0]}, {row[2]:.5f}, {row[3]:.5f})")


def connect_with_retry(client):
    """Próbuje połączyć się z brokerem aż do skutku (broker po starcie potrzebuje chwili)."""
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            return
        except OSError as err:
            print(f"Broker niedostępny ({err}). Próbuję ponownie za 3 s...")
            time.sleep(3)


# --- Start ----------------------------------------------------------------
def main():
    global db
    db = connect_db()
    print(f"Połączono z bazą {DB_HOST}:{DB_PORT}/{DB_NAME}")

    # client_id musi być inny niż w symulatorze, bo dwóch klientów o tej samej nazwie
    # wyrzucałoby się nawzajem z brokera.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fleet-ingestor")
    client.on_connect = on_connect
    client.on_message = on_message
    connect_with_retry(client)

    try:
        client.loop_forever()  # czeka na wiadomości i wywołuje on_message (aż do Ctrl+C)
    except KeyboardInterrupt:
        print("Zatrzymuję ingestor")
    finally:
        client.disconnect()
        db.close()


if __name__ == "__main__":
    main()
