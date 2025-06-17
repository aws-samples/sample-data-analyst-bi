import json
import os
import boto3
from datetime import datetime

# Initialize clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sfn_client = boto3.client('stepfunctions')

# Get environment variables
bucket_name = os.environ.get('S3_BUCKET_NAME')
table_name = os.environ.get('TABLE_NAME')
workflow_arn = os.environ.get('DATA_PROCESSING_WORKFLOW_ARN')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    """
    Handles completion of file uploads and triggers the data processing workflow.
    """
    try:
        # Parse request body
        body = json.loads(event['body']) if isinstance(event.get('body'), str) else event.get('body', {})
        
        # Extract parameters
        project_id = body.get('projectId')
        user_id = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('sub', 'anonymous')
        
        # Validate input
        if not project_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing projectId parameter'})
            }
        
        # Get project details from DynamoDB
        response = table.get_item(
            Key={
                'PK': f"USER#{user_id}",
                'SK': f"PROJECT#{project_id}"
            }
        )
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Project not found'})
            }
        
        project = response['Item']
        data_path = project.get('dataPath')
        
        # Update project status in DynamoDB
        timestamp = datetime.utcnow().isoformat()
        
        table.update_item(
            Key={
                'PK': f"USER#{user_id}",
                'SK': f"PROJECT#{project_id}"
            },
            UpdateExpression="SET #status = :status, updatedAt = :updatedAt",
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'PROCESSING',
                ':updatedAt': timestamp
            }
        )
        
        # Start the Step Functions workflow
        workflow_input = {
            'projectId': project_id,
            'dataPath': data_path
        }
        
        sfn_client.start_execution(
            stateMachineArn=workflow_arn,
            input=json.dumps(workflow_input)
        )
        
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'projectId': project_id,
                'status': 'PROCESSING'
            })
        }
        
    except Exception as e:
        print(f"Error completing upload: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f"Internal server error: {str(e)}"})
        }