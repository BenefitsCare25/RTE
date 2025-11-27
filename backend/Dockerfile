# Use Microsoft's pre-built Playwright image (includes Chromium + all dependencies)
# This saves ~4 minutes of build time by skipping playwright install-deps
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements file first (for better layer caching)
COPY requirements.txt .

# Install Python dependencies
# Note: playwright package is still needed for the Python API
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Render will set $PORT)
EXPOSE 10000

# Start command
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}
