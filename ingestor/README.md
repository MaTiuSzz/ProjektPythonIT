# Ingestor

Mały program w Pythonie, który:

1. łączy się z brokerem MQTT (host z zmiennej `MQTT_HOST`) i subskrybuje `fleet/vehicles/+/gps`,
2. przy każdej wiadomości rozpakowuje JSON (format: patrz README w głównym folderze),
3. zapisuje pozycję do tabeli `positions` w MySQL (host z zmiennej `DB_HOST`, w Dockerze to nazwa usługi `mysql`).

Pole `ts` z wiadomości (ISO z `Z`) trzeba zamienić na czas UTC bez strefy, bo tak przechowuje go kolumna `DATETIME(3)`: `datetime.fromisoformat(ts).astimezone(timezone.utc).replace(tzinfo=None)`. Do połączenia z bazą można użyć `mysql-connector-python`.

Wiadomości od nieistniejących pojazdów (brak wiersza w `vehicles`) należy pomijać z komunikatem w logu.

Do zrobienia: `ingestor.py`, `requirements.txt`, `Dockerfile` oraz odkomentowanie usługi `ingestor` w `docker-compose.yml`.
