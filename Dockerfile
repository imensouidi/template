FROM python:3.9-slim

# Set environment variables
# ENV AZURE_CLIENT_ID="985bbd3e-6294-4b70-8f8c-6dc41e2e9268"
# ENV AZURE_TENANT_ID="1bbea5ff-6a68-4af4-aa7f-2428a8a50adb"
# ENV AZURE_CLIENT_SECRET="JtU8Q~qj64-1l~59op9KGeqUB75j1iO2bCBK9caN"

# Set the working directory in the container
WORKDIR /usr/src/app

# Install unixODBC and unixODBC-devel
RUN apt-get update && apt-get install -y \

# Copy the requirements file to the working directory
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to the working directory
COPY . .

# Expose the Flask port
EXPOSE 5000
EXPOSE 443
EXPOSE 80

# Command to run the Flask application
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]

