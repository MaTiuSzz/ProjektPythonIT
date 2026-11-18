-- Schemat bazy danych systemu zarządzania flotą pojazdów.
--
-- Ten plik wykonuje się AUTOMATYCZNIE, ale tylko przy pierwszym starcie
-- kontenera Postgresa (gdy wolumen z danymi jest jeszcze pusty).
-- Po zmianie schematu trzeba skasować wolumen: docker compose down -v

-- Tabela pojazdów: jeden wiersz = jeden pojazd we flocie.
CREATE TABLE vehicles (
    id     SERIAL PRIMARY KEY,                 -- numer pojazdu (1, 2, 3...), nadawany automatycznie
    plate  VARCHAR(16) NOT NULL UNIQUE,        -- tablica rejestracyjna
    name   VARCHAR(64) NOT NULL,               -- nazwa wyświetlana, np. "Dostawczy A"
    model  VARCHAR(64),                        -- model samochodu (opcjonalnie)
    status VARCHAR(16) NOT NULL DEFAULT 'active'
           CHECK (status IN ('active', 'inactive', 'maintenance'))
);

-- Tabela pozycji GPS: jeden wiersz = jedna wiadomość z pojazdu.
CREATE TABLE positions (
    id         BIGSERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL
               REFERENCES vehicles (id) ON DELETE CASCADE,  -- klucz obcy: pozycja musi należeć do istniejącego pojazdu
    ts         TIMESTAMPTZ NOT NULL,           -- czas pomiaru (z wiadomości MQTT)
    lat        DOUBLE PRECISION NOT NULL,      -- szerokość geograficzna
    lon        DOUBLE PRECISION NOT NULL,      -- długość geograficzna
    speed_kmh  REAL,                           -- prędkość w km/h
    heading    REAL                            -- kierunek jazdy w stopniach (0 = północ, 90 = wschód)
);

-- Indeks przyspiesza zapytania "najnowsza pozycja pojazdu X" i "historia pojazdu X".
CREATE INDEX idx_positions_vehicle_ts ON positions (vehicle_id, ts DESC);

-- Przykładowe pojazdy. Ich numery (1-5) muszą się zgadzać z symulatorem (simulator/simulator.py).
INSERT INTO vehicles (plate, name, model) VALUES
    ('WX 10001', 'Dostawczy A',  'Renault Master'),
    ('WX 10002', 'Dostawczy B',  'Ford Transit'),
    ('WX 10003', 'Osobowy C',    'Skoda Octavia'),
    ('WX 10004', 'Osobowy D',    'Toyota Corolla'),
    ('WX 10005', 'Ciężarowy E',  'Mercedes Sprinter');
