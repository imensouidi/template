# Use the official Python image from the Docker Hub
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PATH_TO_WKHTMLTOPDF=/usr/local/bin/wkhtmltopdf \
    TESSERACT_PATH=/usr/bin/tesseract

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install system dependencies with retries and extended timeout
RUN apt-get update -o Acquire::Retries=5 -o Acquire::http::Timeout="60" && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    wkhtmltopdf \
    curl \
    jq \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 5000

# Run the application
CMD ["python", "convert.py"]
