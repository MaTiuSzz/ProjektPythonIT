-- Schemat bazy danych systemu zarządzania flotą pojazdów (MySQL).
--
-- Ten plik wykonuje się AUTOMATYCZNIE, ale tylko przy pierwszym starcie
-- kontenera MySQL (gdy wolumen z danymi jest jeszcze pusty).
-- Po zmianie schematu trzeba skasować wolumen: docker compose down -v

SET NAMES utf8mb4;  -- polskie znaki (np. "Ciężarowy E") zapisują się poprawnie

-- Tabela pojazdów: jeden wiersz = jeden pojazd we flocie.
CREATE TABLE vehicles (
    id     INT AUTO_INCREMENT PRIMARY KEY,     -- numer pojazdu (1, 2, 3...), nadawany automatycznie
    plate  VARCHAR(16) NOT NULL UNIQUE,        -- tablica rejestracyjna
    name   VARCHAR(64) NOT NULL,               -- nazwa wyświetlana, np. "Dostawczy A"
    model  VARCHAR(64),                        -- model samochodu (opcjonalnie)
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    CONSTRAINT chk_vehicles_status CHECK (status IN ('active', 'inactive', 'maintenance'))
) ENGINE=InnoDB;

-- Tabela pozycji GPS: jeden wiersz = jedna wiadomość z pojazdu.
CREATE TABLE positions (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id INT NOT NULL,
    ts         DATETIME(3) NOT NULL,           -- czas pomiaru w UTC (z wiadomości MQTT), z dokładnością do ms
    lat        DOUBLE NOT NULL,                -- szerokość geograficzna
    lon        DOUBLE NOT NULL,                -- długość geograficzna
    speed_kmh  FLOAT,                          -- prędkość w km/h
    heading    FLOAT,                          -- kierunek jazdy w stopniach (0 = północ, 90 = wschód)
    -- klucz obcy: pozycja musi należeć do istniejącego pojazdu
    CONSTRAINT fk_positions_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles (id) ON DELETE CASCADE,
    -- indeks przyspiesza zapytania "najnowsza pozycja pojazdu X" i "historia pojazdu X"
    INDEX idx_positions_vehicle_ts (vehicle_id, ts DESC)
) ENGINE=InnoDB;

-- Przykładowe pojazdy. Ich numery (1-5) muszą się zgadzać z symulatorem (simulator/simulator.py).
INSERT INTO vehicles (plate, name, model) VALUES
    ('WX 10001', 'Dostawczy A',  'Renault Master'),
    ('WX 10002', 'Dostawczy B',  'Ford Transit'),
    ('WX 10003', 'Osobowy C',    'Skoda Octavia'),
    ('WX 10004', 'Osobowy D',    'Toyota Corolla'),
    ('WX 10005', 'Ciężarowy E',  'Mercedes Sprinter');
