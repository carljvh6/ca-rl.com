FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better Docker layer caching)
COPY infrastructure/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy static files (includes all JSON files)
COPY static/ ./static/

# Verify critical JSON files exist (fail build if missing)
# This ensures files are actually in the image and helps debug build issues
RUN ls -la /app/static/rag/ && \
    test -f /app/static/rag/nedbank_ex_parsed_pdf.json || (echo "ERROR: nedbank_ex_parsed_pdf.json not found!" && ls -la /app/static/rag/ && exit 1) && \
    test -f /app/static/rag/nedbank_int_2024_full_report_parsed.json || (echo "ERROR: nedbank_int_2024_full_report_parsed.json not found!" && ls -la /app/static/rag/ && exit 1) && \
    echo "✓ JSON files verified"

# Build argument for environment
ARG ENV=dev
ENV ENV=${ENV}
ENV PORT=8080

# Expose port (Cloud Run requirement)
EXPOSE 8080

# Run FastHTML app using Uvicorn (ASGI server)
# FastHTML apps are ASGI-compatible
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]



