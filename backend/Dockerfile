# Use Python 3.12.8 base image
FROM python:3.12.8-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright system dependencies and browsers
RUN playwright install-deps chromium && \
    playwright install chromium

# Copy application code
COPY . .

# Expose port (Render will set $PORT)
EXPOSE 10000

# Start command
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}
