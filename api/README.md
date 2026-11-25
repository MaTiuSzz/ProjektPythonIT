# REST API

API we Flasku, które udostępnia dane z bazy MySQL (host z zmiennej `DB_HOST`, w Dockerze to nazwa usługi `mysql`).

Endpointy: patrz tabela w README w głównym folderze. API ma działać na porcie **8000** (`app.run(host="0.0.0.0", port=8000)`), bo taki port jest wystawiony w `docker-compose.yml`.

Wskazówki:

- Do połączenia z bazą można użyć `mysql-connector-python` (oficjalna biblioteka, bez dodatkowych zależności).
- MySQL nie ma `DISTINCT ON`. Ostatnią pozycję każdego pojazdu (`GET /positions/latest`) daje funkcja okna:

```sql
SELECT vehicle_id, ts, lat, lon, speed_kmh, heading
FROM (
    SELECT p.*, ROW_NUMBER() OVER (PARTITION BY vehicle_id ORDER BY ts DESC, id DESC) AS rn
    FROM positions p
) t
WHERE rn = 1;
```

- `ts` w bazie jest w UTC bez strefy. W JSON zwracaj go jako ISO z `Z`, np. `ts.isoformat() + "Z"` (przy `DATETIME(3)` wynik ma milisekundy).
- Mapa (frontend) i API muszą działać pod jednym adresem albo API musi zezwalać na CORS. Najprościej, żeby Flask sam serwował pliki z folderu `frontend/` (inaczej: pakiet `flask-cors`).
- Flask nie ma wbudowanej dokumentacji Swagger. Endpointy można testować w Postmanie albo przez `curl`.

Do zrobienia: `app.py`, `requirements.txt`, `Dockerfile` oraz odkomentowanie usługi `api` w `docker-compose.yml`.
