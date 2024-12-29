FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN mkdir -p /usr/lib/x86_64-linux-gnu/ /var/lib/dpkg /var/lib/dpkg/updates/ /var/lib/dpkg/info/ /var/cache/apt/archives/partial && \
    apt-get update && \
    apt-get install -y \
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
COPY . /app

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5000
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]