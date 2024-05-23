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
    qt5-qmake \
    qtbase5-dev \
    qtbase5-dev-tools \
    libqt5webkit5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    libqt5xmlpatterns5-dev \
    xvfb \
    xfonts-100dpi \
    xfonts-scalable \
    xfonts-cyrillic \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Qt environment variables
ENV QT_SELECT=qt5

# Install wkhtmltopdf from tarball
RUN wget https://github.com/wkhtmltopdf/wkhtmltopdf/archive/refs/tags/0.12.1.tar.gz
RUN tar xvjf 0.12.1.tar.gz
RUN mv 0.12.1.tar /usr/local/bin/wkhtmltopdf
RUN chmod +x /usr/local/bin/wkhtmltopdf

# Verify wkhtmltopdf installation
RUN which wkhtmltopdf

# Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 5000

# Run the application
CMD ["python", "convert.py"]
