FROM python:3.11-slim

WORKDIR /app

# системные зависимости (иногда нужны для gspread / aiohttp)
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
