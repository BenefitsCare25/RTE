# Use Microsoft's pre-built Playwright image (includes Chromium + all dependencies)
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Set working directory
WORKDIR /app

# Install supervisor and git for FlareSolverr
RUN apt-get update && apt-get install -y \
    supervisor \
    git \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Clone FlareSolverr
RUN git clone --depth 1 https://github.com/FlareSolverr/FlareSolverr.git /app/flaresolverr

# Install FlareSolverr dependencies
RUN pip install --no-cache-dir -r /app/flaresolverr/requirements.txt

# Copy requirements file first (for better layer caching)
COPY requirements.txt .

# Install Python dependencies for our API
RUN pip install --no-cache-dir -r requirements.txt

# Copy supervisord configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy application code
COPY . .

# Create log directory
RUN mkdir -p /var/log

# Expose port (Render will set $PORT)
EXPOSE 10000

# Start supervisord to run both FlareSolverr and API
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
