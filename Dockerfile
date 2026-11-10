FROM python:3.11-slim

# Iş katalogyny bellemek
WORKDIR /app

# Python sazlamalary
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TMC_DB_PATH=/app/data/tmc.db

# Baglylyklary gurmak
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Taslamanyň faýllaryny konteýnere geçirmek
COPY . .

# Maglumatlar bazasy üçin katalog
RUN mkdir -p /app/data

# TMC ABCI serwerini işletmek
CMD ["python", "run_tmc.py"]
