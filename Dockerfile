# Use the official Python image from the Docker Hub
FROM python:3.9-slim
ENV AZURE_CLIENT_ID="985bbd3e-6294-4b70-8f8c-6dc41e2e9268"
ENV AZURE_TENANT_ID="1bbea5ff-6a68-4af4-aa7f-2428a8a50adb"
ENV AZURE_CLIENT_SECRET="JtU8Q~qj64-1l~59op9KGeqUB75j1iO2bCBK9caN"

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
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Copy the necessary application files into the container
COPY convert.py .
COPY Background.png .

# Expose the port the app runs on
EXPOSE 5000

# Command to run the application
CMD ["python", "convert.py"]
