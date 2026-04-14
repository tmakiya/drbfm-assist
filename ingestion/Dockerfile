FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code first
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Set Python path to include app directory
ENV PYTHONPATH=/app:$PYTHONPATH

# Create temp directory for intermediate data
RUN mkdir -p /app/temp

# Health check (for pre-flight validation)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default entrypoint (can be overridden by Kubernetes Job)
ENTRYPOINT ["python", "main.py"]

# Default command - will show help if no args provided
CMD ["--help"]
