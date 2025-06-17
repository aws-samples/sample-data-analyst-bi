import json
import os
import boto3
import uuid
from datetime import datetime

# Initialize clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Get environment variables
bucket_name = os.environ.get('S3_BUCKET_NAME')
table_name = os.environ.get('TABLE_NAME')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    """
    Handles file upload requests by generating pre-signed URLs for S3 uploads
    and creating project metadata in DynamoDB.
    """
    try:
        # Parse request body
        body = json.loads(event['body']) if isinstance(event.get('body'), str) else event.get('body', {})
        
        # Extract parameters
        file_name = body.get('fileName')
        file_size = body.get('fileSize')
        content_type = body.get('contentType', 'application/zip')
        user_id = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('sub', 'anonymous')
        
        # Validate input
        if not file_name or not file_size:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameters'})
            }
        
        # Use the filename (without extension) as the project ID
        project_id = os.path.splitext(file_name)[0]
        
        # Create S3 key for the upload
        s3_key = f"{project_id}/{file_name}"
        
        # Generate pre-signed URL for direct upload to S3
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key,
                'ContentType': content_type
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        # Create project metadata in DynamoDB
        timestamp = datetime.utcnow().isoformat()
        
        table.put_item(
            Item={
                'PK': f"USER#{user_id}",
                'SK': f"PROJECT#{project_id}",
                'projectId': project_id,
                'userId': user_id,
                'fileName': file_name,
                'fileSize': file_size,
                'status': 'UPLOADING',
                'createdAt': timestamp,
                'updatedAt': timestamp,
                'dataPath': s3_key
            }
        )
        
        # Return response with presigned URL and project details
        return {
            'statusCode': 200,
            'body': json.dumps({
                'projectId': project_id,
                'uploadUrl': presigned_url,
                'key': s3_key
            })
        }
        
    except Exception as e:
        print(f"Error processing upload request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f"Internal server error: {str(e)}"})
        }