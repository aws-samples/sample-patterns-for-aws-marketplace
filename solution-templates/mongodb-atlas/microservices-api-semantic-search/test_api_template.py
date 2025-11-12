#!/usr/bin/env python3
import boto3
import json
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Detect current AWS region
session = boto3.Session()
current_region = session.region_name

def generate_embedding(text):
    """
    Generate embeddings using AWS Bedrock Titan Text Embeddings V1 model
    """
    bedrock = boto3.client('bedrock-runtime', region_name=current_region)
    
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
        # Fallback to example vector if Bedrock fails
        return [0.1, 0.2, 0.3] + [0.0] * 1533

def make_request(endpoint, data):
    api_url = "${api_url}"
    url = f"{api_url}/{endpoint}"
    
    session = boto3.Session()
    credentials = session.get_credentials()
    
    request = AWSRequest(
        method='POST', 
        url=url, 
        data=json.dumps(data),
        headers={'Content-Type': 'application/json'}
    )
    SigV4Auth(credentials, 'execute-api', current_region).add_auth(request)
    
    response = requests.post(url, data=request.body, headers=dict(request.headers))
    return response.status_code, response.text

if __name__ == "__main__":
    # Test insertOne first
    print("1. Testing insertOne:")
    status, response = make_request("insertOne", {
        "database": "test", 
        "collection": "users",
        "document": {"name": "john_doe", "email": "john@example.com", "age": 30}
    })
    print(f"Status: {status}, Response: {response}")

    # Test find
    print("\n2. Testing find:")
    status, response = make_request("find", {
        "database": "test", 
        "collection": "users"
    })
    print(f"Status: {status}, Response: {response}")

    # Test vector search (requires data to be imported first)
    print("\n3. Testing vector search:")
    query_text = "Find travel recommendations for Asia"
    print(f"Generating embedding for: '{query_text}'")
    query_vector = generate_embedding(query_text)
    
    vector_search_pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "details_embedding",
                "queryVector": query_vector,
                "numCandidates": 100,
                "limit": 5
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
    
    status, response = make_request("aggregate", {
        "database": "travel",
        "collection": "asia", 
        "pipeline": vector_search_pipeline
    })
    print(f"Status: {status}, Response: {response}")
