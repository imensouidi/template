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

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    wget \
    xfonts-75dpi \
    xfonts-base \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install wkhtmltopdf
RUN wget -q https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.6/wkhtmltox_0.12.6-1.bionic_amd64.deb \
    && dpkg -i wkhtmltox_0.12.6-1.bionic_amd64.deb \
    && apt-get install -f \
    && rm wkhtmltox_0.12.6-1.bionic_amd64.deb

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 5000

# Run the application
CMD ["python", "convert.py"]
