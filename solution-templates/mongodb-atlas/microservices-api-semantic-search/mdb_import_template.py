#!/usr/bin/env python3
import csv
import logging
from pymongo import MongoClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('mdb_import')

# MongoDB connection - using direct connection string instead of AWS Secrets Manager
mongodb_uri = "${mongodb_connection_string}"  # Replace with your MongoDB Atlas connection string
logger.info("Connecting to MongoDB Atlas")
client = MongoClient(mongodb_uri)
db = client['travel']
collection = db['asia']

# CSV file path
csv_file_path = './anthropic-travel-agency.trip_recommendations.csv'

logger.info('Starting data import from CSV to MongoDB')

index = 1
with open(csv_file_path, mode='r') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        # logger.debug(f"Processing row type: {type(row)}")
        row['index'] = index
        index += 1
        
        # loop over columns and accumulate all detail_embedding into an array
        detail_embedding = []
        new_row = {}
        for column in row.keys():
            if column.startswith('details_embedding'):
                detail_embedding.append(float(row[column]))
            else:
                new_row[column] = row[column]
        
        new_row['details_embedding'] = detail_embedding
        collection.insert_one(new_row)
        
        if index % 25 == 0:
            logger.info(f'Inserted {index} rows')

logger.info('Finished import successfully')
