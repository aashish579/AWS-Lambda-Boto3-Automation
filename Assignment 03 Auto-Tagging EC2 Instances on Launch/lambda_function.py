import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2_client = boto3.client("ec2")


def lambda_handler(event, context):
    """
    Add governance and ownership tags whenever an EC2 instance
    enters the running state.
    """

    logger.info("Received EventBridge event: %s", json.dumps(event))

    try:
        instance_id = event["detail"]["instance-id"]
        instance_state = event["detail"]["state"]
    except KeyError as error:
        logger.error("Required event field is missing: %s", error)

        return {
            "statusCode": 400,
            "body": json.dumps(
                {
                    "status": "failed",
                    "message": f"Missing event field: {str(error)}"
                }
            )
        }

    if instance_state != "running":
        logger.warning(
            "Ignoring instance %s because state is %s",
            instance_id,
            instance_state
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "ignored",
                    "instance_id": instance_id,
                    "state": instance_state
                }
            )
        }

    launch_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    owner_value = os.environ.get("OWNER_VALUE", "Aashish")
    environment_value = os.environ.get(
        "ENVIRONMENT_VALUE",
        "Development"
    )

    tags = [
        {
            "Key": "LaunchDate",
            "Value": launch_date
        },
        {
            "Key": "Owner",
            "Value": owner_value
        },
        {
            "Key": "Environment",
            "Value": environment_value
        },
        {
            "Key": "TaggedBy",
            "Value": "Lambda-EC2AutoTagger"
        }
    ]

    try:
        ec2_client.create_tags(
            Resources=[instance_id],
            Tags=tags
        )

        logger.info(
            "Successfully tagged EC2 instance %s with tags: %s",
            instance_id,
            json.dumps(tags)
        )

        result = {
            "status": "success",
            "instance_id": instance_id,
            "state": instance_state,
            "tags_applied": tags
        }

        return {
            "statusCode": 200,
            "body": json.dumps(result)
        }

    except ClientError as error:
        logger.exception(
            "Failed to tag EC2 instance %s",
            instance_id
        )

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "failed",
                    "instance_id": instance_id,
                    "error": str(error)
                }
            )
        }