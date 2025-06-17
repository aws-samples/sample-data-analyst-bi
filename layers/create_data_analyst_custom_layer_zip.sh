#!/bin/bash

# Set the directory where the Dockerfile and requirements.txt are located
DIRECTORY="$(pwd)"

# Change it as per your requirement
LAYER_NAME="data-analyst-custom-layer"

echo "Building Data Analyst Lambda layer..."

# Build the Docker image for x86_64 (linux/amd64)
echo "Building Docker image..."
docker buildx build --platform linux/amd64 -t data-analyst-lambda-layer -f Dockerfile-data-analyst "$DIRECTORY" --load

# Run the Docker container for x86_64 (linux/amd64) to create the layer
echo "Creating layer zip file..."
docker run --platform linux/amd64 --name data-analyst-lambda-layer-container -v "$DIRECTORY:/app" data-analyst-lambda-layer

# Stop the container
echo "Cleaning up containers..."
docker stop data-analyst-lambda-layer-container

# Remove the running container
docker rm data-analyst-lambda-layer-container

# Cleanup: remove the Docker image
docker rmi --force data-analyst-lambda-layer

echo "Data Analyst layer created successfully: $DIRECTORY/data-analyst-custom-layer.zip"
