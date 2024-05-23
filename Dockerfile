[12:05 PM] Iheb Ghazala
# Use the official Python image from the Docker Hub based on Debian Buster
FROM python:3.9-buster
 
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
    libxrender1 \
    libxext6 \
    libssl1.1 \
    libcairo2-dev \
    libjpeg62-turbo-dev \
    libpango1.0-dev \
    libgif-dev \
    build-essential \
    g++ \
    libfontconfig1 \
    fontconfig \
    libfontconfig1-dev \
    libqt5core5a \
    libqt5gui5 \
    libqt5widgets5 \
    xvfb \
    xfonts-100dpi \
    xfonts-scalable \
    xfonts-cyrillic \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
 

    RUN apt-get update && apt-get install -yq gdebi

RUN TEMP_DEB="$(mktemp).deb" \
  && wget -O "$TEMP_DEB" 'https://github.com/wkhtmltopdf/packaging/releases/download/0.12.1.4-2/wkhtmltox_0.12.1.4-2.bionic_amd64.deb' \
  && sudo apt install -yqf "$TEMP_DEB" \
  && rm -f "$TEMP_DEB"
# Verify wkhtmltopdf installation
RUN which wkhtmltopdf
 
# Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
 
# Expose the port the app runs on
EXPOSE 5000
 
# Run the application
CMD ["python", "convert.py"]
 