# Przepis na obraz ingestora (taki sam schemat jak w simulator/Dockerfile).
FROM python:3.14-slim

# Wszystko dzieje się w folderze /app wewnątrz kontenera.
WORKDIR /app

# Najpierw biblioteki (osobny krok, żeby Docker mógł je zapamiętać i nie instalować przy każdej zmianie kodu).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Dopiero potem kod programu.
COPY ingestor.py .

# -u wyłącza buforowanie, dzięki czemu logi pojawiają się od razu w "docker compose logs".
CMD ["python", "-u", "ingestor.py"]
