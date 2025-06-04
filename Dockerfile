FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc libpq-dev tesseract-ocr poppler-utils && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
