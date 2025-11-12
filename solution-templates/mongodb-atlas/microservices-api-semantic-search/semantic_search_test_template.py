#!/usr/bin/env python3
import boto3
import json
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Detect current AWS region
session = boto3.Session()
current_region = session.region_name

def make_request(data):
    """
    Make a signed request to the semantic search API
    """
    api_url = "${api_url}"
    url = f"{api_url}/search"
    
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
    print("Testing Semantic Search API")
    
    # Test 1: Simple search query
    print("\n1. Testing search for 'beach vacation':")
    status, response = make_request({
        "query": "beach vacation",
        "limit": 3
    })
    print(f"Status: {status}")
    print(f"Response: {response}")
    
    # Test 2: Different query
    print("\n2. Testing search for 'mountain hiking':")
    status, response = make_request({
        "query": "mountain hiking",
        "limit": 3
    })
    print(f"Status: {status}")
    print(f"Response: {response}")
    
    # Test 3: Cultural attractions
    print("\n3. Testing search for 'temples and culture':")
    status, response = make_request({
        "query": "temples and culture",
        "limit": 5
    })
    print(f"Status: {status}")
    print(f"Response: {response}")
    
    # Test 4: Missing query parameter (should fail)
    print("\n4. Testing with missing query parameter (should fail):")
    status, response = make_request({
        "limit": 5
    })
    print(f"Status: {status}")
    print(f"Response: {response}")
