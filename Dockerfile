# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install system dependencies required for PyMuPDF and other packages
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libpango1.0-dev \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev || true && \
    apt-get -f install && \
    rm -rf /var/lib/apt/lists/*


# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Copy the necessary application files into the container
COPY convert.py .
COPY Background.png .

# Expose the port the app runs on
EXPOSE 5000

# Command to run the application
CMD ["python", "convert.py"]
