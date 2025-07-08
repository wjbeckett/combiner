FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create config directory and set permissions
RUN mkdir -p /config && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /config

USER appuser

# Expose port
EXPOSE 5465

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5465/health || exit 1

# Run the application
CMD ["python", "-m", "app.main"]