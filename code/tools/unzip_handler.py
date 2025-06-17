import json
import os
import boto3
import zipfile
import io

# Initialize S3 client
s3_client = boto3.client('s3')

# Get environment variables
destination_bucket_name = os.environ.get('S3_BUCKET_NAME')  # Destination bucket for extracted files
source_bucket_name = os.environ.get('SOURCE_BUCKET_NAME', destination_bucket_name)  # Source bucket for ZIP files, fallback to destination

def lambda_handler(event, context):
    """
    Extracts files from a zip archive in S3 source bucket and stores them in destination bucket in a project-specific folder.
    """
    try:
        print(f"Event received: {json.dumps(event)}")
        print(f"Source bucket: {source_bucket_name}")
        print(f"Destination bucket: {destination_bucket_name}")
        
        # Extract parameters from the event
        project_id = event.get('projectId')
        data_path = event.get('dataPath')
        
        if not project_id or not data_path:
            raise ValueError("Missing required parameters: projectId or dataPath")
        
        # Download the zip file from S3 source bucket
        print(f"Downloading zip file from S3 source bucket: {source_bucket_name}/{data_path}")
        response = s3_client.get_object(Bucket=source_bucket_name, Key=data_path)
        zip_content = response['Body'].read()
        
        # Extract the zip contents
        extracted_files = []
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
            file_list = zip_ref.namelist()
            print(f"Found {len(file_list)} files in the zip archive")
            
            for file_name in file_list:
                # Skip directories
                if file_name.endswith('/'):
                    continue
                
                # Extract file content
                file_content = zip_ref.read(file_name)
                
                # Determine content type
                content_type = 'text/csv' if file_name.endswith('.csv') else 'application/octet-stream'
                
                # Create S3 key for extracted file
                extracted_key = f"{project_id}/data/{file_name}"
                
                # Upload extracted file to S3 destination bucket
                print(f"Uploading {file_name} to destination bucket: {destination_bucket_name}/{extracted_key}")
                s3_client.put_object(
                    Bucket=destination_bucket_name,
                    Key=extracted_key,
                    Body=file_content,
                    ContentType=content_type
                )
                
                extracted_files.append({
                    'fileName': file_name,
                    's3Key': extracted_key,
                    'destinationBucket': destination_bucket_name
                })
        
        # Return the result
        result = {
            'projectId': project_id,
            'extractedFiles': extracted_files,
            'extractedPath': f"{project_id}/data/",
            'destinationBucket': destination_bucket_name
        }
        
        print(f"Extraction completed successfully: {json.dumps(result)}")
        return result
        
    except Exception as e:
        print(f"Error processing zip file: {str(e)}")
        raise