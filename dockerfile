# Use lightweight Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Install system dependencies
# Including git for private repo access and build tools for pip packages
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Configure git to use token authentication for private repos (optional)
# Build arg for GitHub token (passed during build)
ARG GITHUB_TOKEN
RUN if [ -n "$GITHUB_TOKEN" ]; then \
    git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"; \
    fi

# Copy dependency list first (for better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
# This will use the git config above if GITHUB_TOKEN is set
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy bot code (excluding files in .dockerignore)
COPY . .

# Create logs directory and set up non-root user
RUN useradd -m -u 1000 botuser && \
    mkdir -p /app/logs /app/data && \
    chown -R botuser:botuser /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user for security
USER botuser

# Run bot
CMD ["python", "bot.py"]

