#!/usr/bin/env python3
import json
import boto3
import os
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# Environment variables (set by Terraform)
MONGODB_API_URL = "${mongodb_api_url}"
AWS_REGION = os.environ['AWS_REGION']

def generate_embedding(text):
    """
    Generate embeddings using AWS Bedrock Titan Text Embeddings V1 model
    """
    bedrock = boto3.client('bedrock-runtime', region_name=AWS_REGION)
    
    body = json.dumps({
        "inputText": text
    })
    
    try:
        response = bedrock.invoke_model(
            modelId='amazon.titan-embed-text-v1',
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['embedding']
    
    except Exception as e:
        print(f"Error generating embedding: {e}")
        raise

def call_mongodb_api(pipeline):
    """
    Call MongoDB Data API aggregate endpoint with AWS SigV4 authentication
    """
    url = f"{MONGODB_API_URL}aggregate"
    
    data = {
        "database": "travel",
        "collection": "asia",
        "pipeline": pipeline
    }
    
    # Create AWS request with SigV4 signing
    session = boto3.Session()
    credentials = session.get_credentials()
    
    request = AWSRequest(
        method='POST',
        url=url,
        data=json.dumps(data),
        headers={'Content-Type': 'application/json'}
    )
    SigV4Auth(credentials, 'execute-api', AWS_REGION).add_auth(request)
    
    # Make the request using urllib
    req = Request(url, data=request.body, headers=dict(request.headers))
    
    try:
        with urlopen(req) as response:
            response_data = response.read().decode()
            return json.loads(response_data)
    except HTTPError as e:
        error_body = e.read().decode() if hasattr(e, 'read') else str(e)
        print(f"MongoDB API HTTP Error {e.code}: {error_body}")
        raise Exception(f"MongoDB API error: {e.code}")
    except Exception as e:
        print(f"Error calling MongoDB API: {e}")
        raise

def lambda_handler(event, context):
    """
    Main Lambda handler for semantic search
    
    Expected input:
    {
        "query": "search text",
        "limit": 5  // optional, defaults to 5
    }
    
    Returns:
    {
        "statusCode": 200,
        "body": JSON string with search results
    }
    """
    try:
        # Parse input
        body = json.loads(event.get('body', '{}'))
        query = body.get('query')
        limit = body.get('limit', 5)
        
        if not query:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'query parameter is required'})
            }
        
        # Generate embedding for the query
        print(f"Generating embedding for query: {query}")
        query_vector = generate_embedding(query)
        
        # Construct vector search pipeline (same as test_api_template.py)
        vector_search_pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "details_embedding",
                    "queryVector": query_vector,
                    "numCandidates": 100,
                    "limit": limit
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "index": 1,
                    "Place Name": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]
        
        # Call MongoDB Data API
        print("Calling MongoDB Data API aggregate endpoint")
        result = call_mongodb_api(vector_search_pipeline)
        
        # Return response in same format as test_api.py
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result)
        }
        
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Internal server error'})
        }
