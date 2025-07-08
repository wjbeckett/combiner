FROM python:3.11-slim

# Install required system packages
RUN apt-get update && apt-get install -y \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create config directory
RUN mkdir -p /config

# Set default environment variables
ENV PUID=1000
ENV PGID=1000
ENV UMASK=022

# Expose port
EXPOSE 5465

# Use entrypoint script
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
