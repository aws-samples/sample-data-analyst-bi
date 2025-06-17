import json
import os
import boto3
import decimal
from boto3.dynamodb.conditions import Key

# Helper class to convert Decimal to JSON serializable format
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super(DecimalEncoder, self).default(o)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Get environment variables
table_name = os.environ.get('TABLE_NAME')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    """
    Lists all projects for a user.
    """
    try:
        # Get user ID from the request
        user_id = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('sub', 'anonymous')
        
        # Query DynamoDB for user's projects
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"USER#{user_id}") & Key('SK').begins_with("PROJECT#")
        )
        
        # Format the response
        projects = []
        for item in response.get('Items', []):
            projects.append({
                'projectId': item.get('projectId'),
                'fileName': item.get('fileName'),
                'fileSize': item.get('fileSize'),
                'status': item.get('status'),
                'createdAt': item.get('createdAt'),
                'updatedAt': item.get('updatedAt')
            })
        
        # Return the list of projects
        return {
            'statusCode': 200,
            'body': json.dumps({
                'projects': projects
            }, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"Error listing projects: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f"Internal server error: {str(e)}"}, cls=DecimalEncoder)
        }