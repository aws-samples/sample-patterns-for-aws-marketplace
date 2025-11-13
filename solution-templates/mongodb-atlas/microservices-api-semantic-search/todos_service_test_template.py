#!/usr/bin/env python3
import boto3
import json
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Detect current AWS region
session = boto3.Session()
current_region = session.region_name

def make_request(method, path, data=None):
    """
    Make a signed request to the Todos API
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API path (e.g., '/todos' or '/todos/{id}')
        data: Request body (optional)
    
    Returns:
        Tuple of (status_code, response_text)
    """
    api_url = "${api_url}"
    url = f"{api_url}{path}"
    
    session = boto3.Session()
    credentials = session.get_credentials()
    
    request_body = json.dumps(data) if data else None
    
    request = AWSRequest(
        method=method,
        url=url,
        data=request_body,
        headers={'Content-Type': 'application/json'} if request_body else {}
    )
    SigV4Auth(credentials, 'execute-api', current_region).add_auth(request)
    
    response = requests.request(
        method,
        url,
        data=request.body,
        headers=dict(request.headers)
    )
    return response.status_code, response.text

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Todos Service API")
    print("=" * 60)
    
    created_todo_id = None
    
    # Test 1: Create a new todo
    print("\n1. Creating a new todo:")
    print("-" * 60)
    status, response = make_request('POST', '/todos', {
        "title": "Complete workshop",
        "description": "Finish the MongoDB Atlas REST API workshop"
    })
    print(f"Status: {status}")
    print(f"Response: {response}")
    
    if status == 201:
        response_data = json.loads(response)
        created_todo_id = response_data.get('insertedId')
        print(f"Created todo ID: {created_todo_id}")
    
    # Test 2: Create another todo
    print("\n2. Creating another todo:")
    print("-" * 60)
    status, response = make_request('POST', '/todos', {
        "title": "Test API endpoints",
        "description": "Verify all CRUD operations work correctly"
    })
    print(f"Status: {status}")
    print(f"Response: {response}")
    
    # Test 3: List all todos
    print("\n3. Listing all todos:")
    print("-" * 60)
    status, response = make_request('GET', '/todos')
    print(f"Status: {status}")
    print(f"Response: {response}")
    
    # Test 4: Update a todo (if we created one)
    if created_todo_id:
        print(f"\n4. Updating todo (ID: {created_todo_id}):")
        print("-" * 60)
        status, response = make_request('PUT', f'/todos/{created_todo_id}', {
            "completed": True,
            "description": "Workshop completed successfully!"
        })
        print(f"Status: {status}")
        print(f"Response: {response}")
    
    # Test 5: Delete a todo (if we created one)
    if created_todo_id:
        print(f"\n5. Deleting todo (ID: {created_todo_id}):")
        print("-" * 60)
        status, response = make_request('DELETE', f'/todos/{created_todo_id}')
        print(f"Status: {status}")
        print(f"Response: {response}")
    
    # Test 6: Create todo with missing title (should fail)
    print("\n6. Creating todo without title (should fail):")
    print("-" * 60)
    status, response = make_request('POST', '/todos', {
        "description": "This should fail"
    })
    print(f"Status: {status}")
    print(f"Response: {response}")
    
    # Test 7: List all remaining todos
    print("\n7. Final list of all todos:")
    print("-" * 60)
    status, response = make_request('GET', '/todos')
    print(f"Status: {status}")
    print(f"Response: {response}")
    
    print("\n" + "=" * 60)
    print("Test suite completed")
    print("=" * 60)
