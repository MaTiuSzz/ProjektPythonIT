# Ingestor

Mały program w Pythonie, który:

1. łączy się z brokerem MQTT (host z zmiennej `MQTT_HOST`) i subskrybuje `fleet/vehicles/+/gps`,
2. przy każdej wiadomości rozpakowuje JSON (format: patrz README w głównym folderze),
3. zapisuje pozycję do tabeli `positions` w MySQL (host z zmiennej `DB_HOST`, w Dockerze to nazwa usługi `mysql`).

Pole `ts` z wiadomości (ISO z `Z`) trzeba zamienić na czas UTC bez strefy, bo tak przechowuje go kolumna `DATETIME(3)`: `datetime.fromisoformat(ts).astimezone(timezone.utc).replace(tzinfo=None)`. Do połączenia z bazą można użyć `mysql-connector-python`.

Wiadomości od nieistniejących pojazdów (brak wiersza w `vehicles`) należy pomijać z komunikatem w logu.

Pliki: `ingestor.py` (kod), `requirements.txt` (biblioteki), `Dockerfile` (obraz). Usługa `ingestor` jest opisana w `docker-compose.yml`.

Uruchomienie w Dockerze razem z resztą: `docker compose up --build -d` w głównym folderze projektu.

Uruchomienie lokalnie (np. do debugowania), przy włączonym brokerze i bazie z Dockera. Port bazy na komputerze to 3307:

```
$env:DB_PORT="3307"
py ingestor/ingestor.py
```

Uwaga: nie uruchamiaj jednocześnie ingestora lokalnie i w Dockerze, bo oba mają ten sam `client_id` w brokerze i wyrzucałyby się nawzajem.
