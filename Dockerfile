FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set Python path to include src directory and root
ENV PYTHONPATH=/app:/app/src:$PYTHONPATH

# Default command (can be overridden in Railway)
CMD ["python", "websocket_limit_trading.py"]
