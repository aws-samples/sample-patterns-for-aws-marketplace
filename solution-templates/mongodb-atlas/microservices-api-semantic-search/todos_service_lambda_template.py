#!/usr/bin/env python3
import json
import boto3
import os
from datetime import datetime
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# Environment variables (set by Terraform)
MONGODB_API_URL = "${mongodb_api_url}"
AWS_REGION = os.environ['AWS_REGION']

def call_mongodb_api(endpoint, data):
    """
    Call MongoDB Data API with AWS SigV4 authentication
    
    Args:
        endpoint: MongoDB API endpoint (e.g., 'insertOne', 'find', 'updateOne', 'deleteOne')
        data: Request payload for the MongoDB API
    
    Returns:
        Response from MongoDB API
    """
    url = f"{MONGODB_API_URL}{endpoint}"
    
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

def list_todos():
    """
    List all todos from MongoDB
    """
    data = {
        "database": "todos",
        "collection": "items",
        "filter": {}
    }
    
    result = call_mongodb_api('find', data)
    return result.get('documents', [])

def get_todo_by_id(todo_id):
    """
    Get a specific todo by ID
    """
    data = {
        "database": "todos",
        "collection": "items",
        "filter": {"_id": todo_id}
    }
    
    result = call_mongodb_api('findOne', data)
    return result.get('document')

def create_todo(title, description=None):
    """
    Create a new todo
    """
    now = datetime.utcnow().isoformat()
    
    document = {
        "title": title,
        "description": description or "",
        "completed": False,
        "created_at": now,
        "updated_at": now
    }
    
    data = {
        "database": "todos",
        "collection": "items",
        "document": document
    }
    
    result = call_mongodb_api('insertOne', data)
    return result

def update_todo(todo_id, updates):
    """
    Update an existing todo
    """
    # Add updated_at timestamp
    updates['updated_at'] = datetime.utcnow().isoformat()
    
    data = {
        "database": "todos",
        "collection": "items",
        "filter": {"_id": todo_id},
        "update": {"$set": updates}
    }
    
    result = call_mongodb_api('updateOne', data)
    return result

def delete_todo(todo_id):
    """
    Delete a todo by ID
    """
    data = {
        "database": "todos",
        "collection": "items",
        "filter": {"_id": todo_id}
    }
    
    result = call_mongodb_api('deleteOne', data)
    return result

def lambda_handler(event, context):
    """
    Main Lambda handler for Todos Service
    
    Handles CRUD operations for todos:
    - GET /todos - List all todos
    - GET /todos/{id} - Get specific todo
    - POST /todos - Create new todo
    - PUT /todos/{id} - Update existing todo
    - DELETE /todos/{id} - Delete todo
    """
    try:
        http_method = event.get('httpMethod')
        path = event.get('path', '')
        path_parameters = event.get('pathParameters') or {}
        
        print(f"Processing {http_method} request to {path}")
        
        # GET /todos or GET /todos/{id}
        if http_method == 'GET':
            todo_id = path_parameters.get('id')
            
            if todo_id:
                # Get specific todo
                todo = get_todo_by_id(todo_id)
                if todo:
                    return {
                        'statusCode': 200,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps(todo)
                    }
                else:
                    return {
                        'statusCode': 404,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({'error': 'Todo not found'})
                    }
            else:
                # List all todos
                todos = list_todos()
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'todos': todos})
                }
        
        # POST /todos - Create new todo
        elif http_method == 'POST':
            body = json.loads(event.get('body', '{}'))
            title = body.get('title')
            description = body.get('description')
            
            if not title:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'title is required'})
                }
            
            result = create_todo(title, description)
            return {
                'statusCode': 201,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(result)
            }
        
        # PUT /todos/{id} - Update existing todo
        elif http_method == 'PUT':
            todo_id = path_parameters.get('id')
            if not todo_id:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'todo id is required'})
                }
            
            body = json.loads(event.get('body', '{}'))
            updates = {}
            
            if 'title' in body:
                updates['title'] = body['title']
            if 'description' in body:
                updates['description'] = body['description']
            if 'completed' in body:
                updates['completed'] = body['completed']
            
            if not updates:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'No fields to update'})
                }
            
            result = update_todo(todo_id, updates)
            
            if result.get('modifiedCount', 0) > 0:
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps(result)
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'Todo not found'})
                }
        
        # DELETE /todos/{id} - Delete todo
        elif http_method == 'DELETE':
            todo_id = path_parameters.get('id')
            if not todo_id:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'todo id is required'})
                }
            
            result = delete_todo(todo_id)
            
            if result.get('deletedCount', 0) > 0:
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'message': 'Todo deleted successfully'})
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'Todo not found'})
                }
        
        else:
            return {
                'statusCode': 405,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Method not allowed'})
            }
    
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Internal server error', 'details': str(e)})
        }
