#!/bin/bash

# Set the directory where the Dockerfile and requirements.txt are located
DIRECTORY="$(pwd)"

# Change it as per your requirement
LAYER_NAME="querybot-custom-layer"

echo "Building QueryBot Lambda layer with pandas, psycopg2, s3fs, and openpyxl..."

# Build the Docker image for x86_64 (linux/amd64)
echo "Building Docker image..."
docker buildx build --platform linux/amd64 -t querybot-lambda-layer -f Dockerfile-querybot "$DIRECTORY" --load

# Run the Docker container for x86_64 (linux/amd64) to create the layer
echo "Creating layer zip file..."
docker run --platform linux/amd64 --name querybot-lambda-layer-container -v "$DIRECTORY:/app" querybot-lambda-layer

# Stop the container
echo "Cleaning up containers..."
docker stop querybot-lambda-layer-container

# Remove the running container
docker rm querybot-lambda-layer-container

# Cleanup: remove the Docker image
docker rmi --force querybot-lambda-layer

echo "QueryBot layer created successfully: $DIRECTORY/querybot-custom-layer.zip"
echo "You can now deploy this layer to AWS Lambda." 