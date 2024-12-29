# Use a base image
FROM python:3.9-slim

# Set environment variables to reduce prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Reset dpkg and clean apt state
RUN rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* /var/lib/dpkg/updates/* && \
    mkdir -p /var/lib/apt/lists/partial /var/cache/apt/archives/partial /var/lib/dpkg/updates/ && \
    touch /var/lib/dpkg/status && \
    apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libpango1.0-dev \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    libjpeg-dev \
    libpq-dev \
    fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
WORKDIR /app
COPY . /app

# Install Python dependencies
RUN pip install -r requirements.txt

# Expose port and run the app
EXPOSE 5000
CMD ["python", "app.py"]
