"""
Symulator pojazdów floty.

Co sekundę wysyła pozycję GPS każdego pojazdu do brokera MQTT.
Pojazdy jeżdżą w pętli po zadanych punktach w Warszawie (po liniach prostych,
a nie po prawdziwych drogach - na potrzeby projektu to w zupełności wystarczy).

Topic i format wiadomości są opisane w README.md (sekcja "Kontrakt").
"""

import json
import math
import os
import random
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# --- Konfiguracja ---------------------------------------------------------
# Wartości można zmienić zmiennymi środowiskowymi, bez ruszania kodu.
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")  # w Dockerze: "broker" (nazwa usługi z docker-compose)
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
INTERVAL_S = float(os.getenv("PUBLISH_INTERVAL", "1.0"))  # co ile sekund wysyłać pozycje
TOPIC = "fleet/vehicles/{vehicle_id}/gps"
QOS = 1  # 1 = wiadomość zostanie dostarczona co najmniej raz

# --- Dane pojazdów --------------------------------------------------------
# Klucz to numer pojazdu - musi się zgadzać z tabelą vehicles w db/init.sql.
# Wartość to (prędkość bazowa w km/h, lista punktów trasy jako (lat, lon)).
VEHICLES = {
    1: (40, [(52.2297, 21.0122), (52.2370, 21.0175), (52.2410, 21.0050), (52.2330, 20.9990)]),  # Śródmieście
    2: (55, [(52.2000, 21.0200), (52.2100, 21.0300), (52.2150, 21.0100), (52.2050, 21.0000)]),  # Mokotów
    3: (45, [(52.2500, 21.0400), (52.2450, 21.0550), (52.2350, 21.0500), (52.2380, 21.0350)]),  # Praga
    4: (60, [(52.2350, 20.9700), (52.2400, 20.9550), (52.2300, 20.9450), (52.2250, 20.9600)]),  # Wola
    5: (35, [(52.2700, 20.9850), (52.2750, 20.9950), (52.2650, 21.0000), (52.2620, 20.9880)]),  # Żoliborz
}

EARTH_RADIUS_M = 6_371_000


# --- Funkcje pomocnicze (geometria) ---------------------------------------
def distance_m(lat1, lon1, lat2, lon2):
    """Odległość w metrach między dwoma punktami GPS (wzór haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Kierunek jazdy w stopniach: 0 = północ, 90 = wschód, 180 = południe, 270 = zachód."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# --- Pojazd ---------------------------------------------------------------
class Vehicle:
    """Jeden symulowany pojazd, który jedzie w pętli po punktach swojej trasy."""

    def __init__(self, vehicle_id, base_speed_kmh, route):
        self.id = vehicle_id
        self.base_speed_kmh = base_speed_kmh
        self.route = route
        self.lat, self.lon = route[0]  # start w pierwszym punkcie trasy
        self.target = 1                # indeks punktu, do którego aktualnie jedziemy
        self.speed_kmh = base_speed_kmh
        self.heading = 0.0

    def move(self, dt_s):
        """Przesuwa pojazd o dystans przejechany w czasie dt_s sekund."""
        # Prędkość lekko się waha, żeby dane wyglądały realistycznie.
        self.speed_kmh = self.base_speed_kmh * random.uniform(0.85, 1.15)
        step_m = self.speed_kmh / 3.6 * dt_s  # km/h -> m/s -> metry przejechane w tym kroku

        target_lat, target_lon = self.route[self.target]
        dist_m = distance_m(self.lat, self.lon, target_lat, target_lon)
        self.heading = bearing_deg(self.lat, self.lon, target_lat, target_lon)

        if step_m >= dist_m:
            # Dojechaliśmy do punktu: ustaw się dokładnie w nim i wybierz następny (po ostatnim wracamy do pierwszego).
            self.lat, self.lon = target_lat, target_lon
            self.target = (self.target + 1) % len(self.route)
        else:
            # Jeszcze nie dojechaliśmy: przesuń się o ułamek drogi do punktu.
            ratio = step_m / dist_m
            self.lat += (target_lat - self.lat) * ratio
            self.lon += (target_lon - self.lon) * ratio


# --- MQTT -----------------------------------------------------------------
def make_message(vehicle):
    """Buduje wiadomość w formacie ustalonym w README (sekcja 'Kontrakt')."""
    return {
        "vehicle_id": vehicle.id,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),  # czas UTC
        "lat": round(vehicle.lat, 6),
        "lon": round(vehicle.lon, 6),
        "speed_kmh": round(vehicle.speed_kmh, 1),
        "heading": round(vehicle.heading),
    }


# Flaga "połączono" - pozwala poczekać w main(), aż broker potwierdzi połączenie.
connected = threading.Event()


def on_connect(client, userdata, flags, reason_code, properties):
    """Wywoływana przez bibliotekę, gdy połączenie z brokerem zostanie nawiązane (też po ponownym połączeniu)."""
    print(f"Połączono z brokerem {MQTT_HOST}:{MQTT_PORT} (kod: {reason_code})")
    connected.set()


def connect_with_retry(client):
    """Próbuje połączyć się z brokerem aż do skutku (broker po starcie potrzebuje chwili)."""
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            return
        except OSError as err:
            print(f"Broker niedostępny ({err}). Próbuję ponownie za 3 s...")
            time.sleep(3)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fleet-simulator")
    client.on_connect = on_connect
    connect_with_retry(client)
    client.loop_start()  # obsługa sieci w osobnym wątku, w tle
    connected.wait(timeout=10)  # czekamy na potwierdzenie połączenia od brokera

    vehicles = [Vehicle(vid, speed, route) for vid, (speed, route) in VEHICLES.items()]
    print(f"Symulator startuje: {len(vehicles)} pojazdów, wysyłam co {INTERVAL_S} s")

    try:
        while True:
            for vehicle in vehicles:
                vehicle.move(INTERVAL_S)
                message = make_message(vehicle)
                client.publish(TOPIC.format(vehicle_id=vehicle.id), json.dumps(message), qos=QOS)
            first = vehicles[0]
            print(f"[{time.strftime('%H:%M:%S')}] wysłano {len(vehicles)} pozycji "
                  f"(pojazd {first.id}: {first.lat:.5f}, {first.lon:.5f})")
            time.sleep(INTERVAL_S)
    except KeyboardInterrupt:
        print("Zatrzymuję symulator")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
