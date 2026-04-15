FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create directories needed at runtime
RUN mkdir -p static/pdf_reports instance

# Expose port
EXPOSE 10000

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Initialize the database with seed data on image build
RUN python init_db.py

# Start with gunicorn (reads $PORT env var, defaults to 10000)
CMD gunicorn -b 0.0.0.0:${PORT:-10000} --workers=2 --timeout=120 app:app