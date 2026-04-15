FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p static/pdf_reports instance

RUN python init_db.py

CMD gunicorn -b 0.0.0.0:${PORT:-10000} app:app