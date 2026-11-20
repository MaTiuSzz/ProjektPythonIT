# Notatka od osoby B (API) dla osoby A i jej asystenta AI

Stan na 20.11.2026. Kontekst: projekt "System zarządzania flotą pojazdów" (temat 12, Python w zastosowaniach IT, PW). Osoba A = dane i infrastruktura (compose, broker, symulator, ingestor, init.sql). Osoba B = API i frontend. Prezentacja przebiegu prac: wtorek 24.11.

## Co zrobiła osoba B

Branch `feature/api` (wypchnięty na GitHub, **PR do `main` jeszcze nie ma**), dwa commity:
- `6214c36` API: GET /vehicles i GET /positions/latest
- `52302bc` API: pełny CRUD pojazdów i historia pozycji

Nowe pliki (tylko w `api/`, poza `api/` nic nie było zmieniane):
- `api/requirements.txt`: `fastapi>=0.115,<1`, `uvicorn[standard]>=0.32,<1`, `psycopg[binary]>=3.2,<4` (psycopg 3, czysty SQL, bez ORM)
- `api/main.py`: całe API w jednym pliku, z komentarzami po polsku

## Endpointy (zgodne z kontraktem z README)

| Endpoint | Sukces | Błędy |
|---|---|---|
| `GET /health` | 200 `{"status":"ok"}` (nie dotyka bazy) | |
| `GET /vehicles` | 200, lista | |
| `POST /vehicles` | 201, utworzony pojazd z `id` | 409 tablica zajęta, 422 złe dane |
| `GET /vehicles/{id}` | 200 | 404 |
| `PUT /vehicles/{id}` | 200 (wymaga wszystkich pól) | 404, 409, 422 |
| `DELETE /vehicles/{id}` | 204 (pozycje znikają przez `ON DELETE CASCADE`) | 404 |
| `GET /positions/latest` | 200, ostatnia pozycja każdego pojazdu (`DISTINCT ON`) | |
| `GET /vehicles/{id}/history?from=&to=` | 200, pozycje rosnąco po `ts`; `from`/`to` opcjonalne, ISO 8601 | 404 brak pojazdu, 422 zła data lub `from > to` |

Szczegóły zachowania:
- Pojazd bez żadnych pozycji: nie występuje w `/positions/latest`, a jego `/history` zwraca `[]` (nie 404).
- `status` walidowany przez Pydantic jako `active` / `inactive` / `maintenance`, tak samo jak `CHECK` w `db/init.sql`. Limity długości pól są takie same jak `VARCHAR` w schemacie.
- `ts` w odpowiedziach jest w UTC, np. `2026-11-20T12:07:30.760256Z`.

Przetestowano ręcznie 20 przypadków (poprawne i błędne) na lokalnym Postgresie z compose. Wszystkie dały oczekiwane kody.

## Konfiguracja API (ważne przy dopisywaniu usługi `api` do compose)

API czyta zmienne środowiskowe, a wartości domyślne są takie same jak w `docker-compose.yml`:

| Zmienna | Domyślnie |
|---|---|
| `DB_HOST` | `localhost` |
| `DB_PORT` | `5432` |
| `POSTGRES_DB` | `fleet` |
| `POSTGRES_USER` | `fleet` |
| `POSTGRES_PASSWORD` | `fleet_dev_pass` |

**Uwaga:** zakomentowany szkic usługi `api` w compose ma tylko `DB_HOST: postgres`. To działa dzięki wartościom domyślnym, ale jeśli ktoś ustawi własne hasło w `.env`, API go nie dostanie. Przy odkomentowaniu trzeba dopisać `POSTGRES_DB`, `POSTGRES_USER` i `POSTGRES_PASSWORD` (np. `${POSTGRES_PASSWORD:-fleet_dev_pass}`, tak jak przy usłudze `postgres`).

## Czego jeszcze NIE ma (plan na poniedziałek 23.11, wspólnie)

- `api/Dockerfile` (wzorem `simulator/Dockerfile`, `python:3.14-slim`, start: `uvicorn main:app --host 0.0.0.0 --port 8000`; `--host 0.0.0.0` jest konieczne w kontenerze)
- odkomentowanie usługi `api` w `docker-compose.yml` (z poprawką z sekcji wyżej)
- `docker compose up --build` całości i przejście demo: symulator, MQTTX, ingestor, baza, Swagger
- PR `feature/api` → `main` i review przez osobę A
- frontend (mapa Leaflet, serwowana przez API jako plik statyczny): po wtorku

Do sprawdzenia przy integracji: B testował lokalnie na Pythonie 3.13, a w kontenerze będzie 3.14. Nie powinno być różnicy, ale warto zwrócić uwagę na build obrazu.

## Uwagi i propozycje dla osoby A (do decyzji, nic z tego nie zostało zmienione)

1. **Duplikaty pozycji przy QoS 1.** W `positions` nie ma `UNIQUE (vehicle_id, ts)`, więc ponownie dostarczona wiadomość zapisze się dwa razy. Propozycja: `UNIQUE (vehicle_id, ts)` w `init.sql` i `INSERT ... ON CONFLICT DO NOTHING` w ingestorze. Na MVP nie jest to konieczne.
2. **Ingestor a `vehicle_id`.** Zgodnie z `ingestor/README.md` wiadomości od nieistniejących pojazdów trzeba pomijać. Jeśli przez API usunie się auto 1–5, symulator dalej będzie je wysyłał, a ingestor musi to przeżyć (wyjątek `ForeignKeyViolation`) i nie może się wysypać.
3. **Rozmiar historii.** `/history` bez `from`/`to` zwraca całą historię (przy 1 wiadomości/s to 3600 wierszy na auto na godzinę). Na demo nie jest to problem. Ewentualny domyślny limit trzeba ustalić wspólnie, bo zmienia kontrakt.

## Stan lokalnej bazy u B (nie dotyczy repo)

U osoby B wolumen `pgdata` ma ręcznie wpisane 6 testowych pozycji (auta 1–3) i sekwencja `vehicles.id` jest przesunięta na 7 (po testowym dodaniu i usunięciu auta). Te dane nie trafiły do repo. U A baza z `init.sql` będzie czysta.

## Prośba

Nie zmieniać kontraktu (topic, payload, schemat bazy, endpointy) bez uzgodnienia z osobą B. Zmiany w `api/` najlepiej zgłaszać przez review PR-a.
