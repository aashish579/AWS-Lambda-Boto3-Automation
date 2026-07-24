import json
import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create S3 client
s3 = boto3.client("s3")


def lambda_handler(event, context):
    bucket_name = os.environ["BUCKET_NAME"]
    retention_days = int(os.environ.get("RETENTION_DAYS", "30"))
    test_minutes = int(os.environ.get("TEST_RETENTION_MINUTES", "0"))

    # Current UTC time
    current_time = datetime.now(timezone.utc)

    # Testing mode (minutes) or Production mode (days)
    if test_minutes > 0:
        cutoff_time = current_time - timedelta(minutes=test_minutes)
        logger.info(f"TEST MODE: Objects older than {test_minutes} minute(s) will be deleted.")
    else:
        cutoff_time = current_time - timedelta(days=retention_days)
        logger.info(f"PRODUCTION MODE: Objects older than {retention_days} day(s) will be deleted.")

    deleted_objects = []
    retained_objects = []
    scanned = 0

    try:
        paginator = s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=bucket_name):

            if "Contents" not in page:
                continue

            for obj in page["Contents"]:

                scanned += 1

                key = obj["Key"]
                last_modified = obj["LastModified"]

                logger.info(f"Checking object: {key}")

                if last_modified < cutoff_time:

                    s3.delete_object(
                        Bucket=bucket_name,
                        Key=key
                    )

                    deleted_objects.append(key)

                    logger.info(f"Deleted: {key}")

                else:

                    retained_objects.append(key)

                    logger.info(f"Retained: {key}")

        result = {
            "Status": "Success",
            "Bucket": bucket_name,
            "ObjectsScanned": scanned,
            "DeletedObjects": deleted_objects,
            "RetainedObjects": retained_objects
        }

        logger.info(json.dumps(result))

        return {
            "statusCode": 200,
            "body": json.dumps(result)
        }

    except ClientError as e:

        logger.error(str(e))

        return {
            "statusCode": 500,
            "body": json.dumps(str(e))
        }