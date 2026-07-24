import json
import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create EC2 client
ec2 = boto3.client("ec2")


def lambda_handler(event, context):

    volume_id = os.environ["VOLUME_ID"]
    retention_days = int(os.environ.get("RETENTION_DAYS", "30"))
    test_minutes = int(os.environ.get("TEST_RETENTION_MINUTES", "0"))

    current_time = datetime.now(timezone.utc)

    # ---------- Create Snapshot ----------

    try:

        snapshot = ec2.create_snapshot(
            VolumeId=volume_id,
            Description="Automated Snapshot created by Lambda"
        )

        snapshot_id = snapshot["SnapshotId"]

        logger.info(f"Snapshot Created : {snapshot_id}")

        # Add Tag

        ec2.create_tags(
            Resources=[snapshot_id],
            Tags=[
                {
                    "Key": "CreatedBy",
                    "Value": "Lambda-Backup"
                }
            ]
        )

        logger.info("Tag Applied Successfully")

    except ClientError as e:

        logger.error(f"Snapshot Creation Failed : {str(e)}")

        return {
            "statusCode": 500,
            "body": str(e)
        }

    # ---------- Decide Retention ----------

    if test_minutes > 0:

        cutoff = current_time - timedelta(minutes=test_minutes)

        logger.info(
            f"TEST MODE : Delete snapshots older than {test_minutes} minute(s)"
        )

    else:

        cutoff = current_time - timedelta(days=retention_days)

        logger.info(
            f"PRODUCTION MODE : Delete snapshots older than {retention_days} days"
        )

    deleted = []

    # ---------- Find Snapshots ----------

    try:

        snapshots = ec2.describe_snapshots(
            OwnerIds=["self"],
            Filters=[
                {
                    "Name": "tag:CreatedBy",
                    "Values": ["Lambda-Backup"]
                }
            ]
        )

        for snap in snapshots["Snapshots"]:

            if snap["SnapshotId"] == snapshot_id:
                continue

            if snap["StartTime"] < cutoff:

                ec2.delete_snapshot(
                    SnapshotId=snap["SnapshotId"]
                )

                deleted.append(snap["SnapshotId"])

                logger.info(
                    f"Deleted Snapshot : {snap['SnapshotId']}"
                )

    except ClientError as e:

        logger.error(str(e))

        return {
            "statusCode": 500,
            "body": str(e)
        }

    result = {

        "CreatedSnapshot": snapshot_id,
        "DeletedSnapshots": deleted,
        "RetentionDays": retention_days

    }

    logger.info(json.dumps(result))

    return {

        "statusCode": 200,
        "body": json.dumps(result)

    }