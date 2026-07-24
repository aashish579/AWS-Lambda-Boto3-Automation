import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError, WaiterError


logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2 = boto3.client("ec2")


def get_latest_snapshot(volume_id):
    """
    Return the most recent completed snapshot for the specified EBS volume.
    """
    response = ec2.describe_snapshots(
        OwnerIds=["self"],
        Filters=[
            {
                "Name": "volume-id",
                "Values": [volume_id]
            },
            {
                "Name": "status",
                "Values": ["completed"]
            }
        ]
    )

    snapshots = response.get("Snapshots", [])

    if not snapshots:
        raise ValueError(
            f"No completed snapshots found for volume {volume_id}"
        )

    latest_snapshot = max(
        snapshots,
        key=lambda snapshot: snapshot["StartTime"]
    )

    logger.info(
        "Latest snapshot selected: %s, StartTime: %s",
        latest_snapshot["SnapshotId"],
        latest_snapshot["StartTime"]
    )

    return latest_snapshot


def register_ami(snapshot_id, root_device_name, architecture):
    """
    Register an EBS-backed Linux AMI using the selected root snapshot.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    image_name = f"lambda-restored-ami-{timestamp}"

    response = ec2.register_image(
        Name=image_name,
        Description=(
            f"Temporary recovery AMI registered by Lambda "
            f"from snapshot {snapshot_id}"
        ),
        Architecture=architecture,
        RootDeviceName=root_device_name,
        VirtualizationType="hvm",
        EnaSupport=True,
        BlockDeviceMappings=[
            {
                "DeviceName": root_device_name,
                "Ebs": {
                    "SnapshotId": snapshot_id,
                    "DeleteOnTermination": True,
                    "VolumeType": "gp3"
                }
            }
        ],
        TagSpecifications=[
            {
                "ResourceType": "image",
                "Tags": [
                    {
                        "Key": "CreatedBy",
                        "Value": "Lambda-EC2-Restore"
                    },
                    {
                        "Key": "SourceSnapshot",
                        "Value": snapshot_id
                    }
                ]
            }
        ]
    )

    image_id = response["ImageId"]

    logger.info(
        "AMI registered successfully. ImageId: %s",
        image_id
    )

    return image_id


def wait_for_ami(image_id):
    """
    Wait until the registered AMI becomes available.
    """
    logger.info("Waiting for AMI %s to become available", image_id)

    waiter = ec2.get_waiter("image_available")

    waiter.wait(
        ImageIds=[image_id],
        WaiterConfig={
            "Delay": 10,
            "MaxAttempts": 24
        }
    )

    logger.info("AMI is now available: %s", image_id)


def launch_restored_instance(
    image_id,
    snapshot_id,
    subnet_id,
    security_group_id,
    key_name,
    instance_type
):
    """
    Launch and tag one EC2 instance from the registered recovery AMI.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = ec2.run_instances(
        ImageId=image_id,
        InstanceType=instance_type,
        MinCount=1,
        MaxCount=1,
        SubnetId=subnet_id,
        SecurityGroupIds=[security_group_id],
        KeyName=key_name,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {
                        "Key": "Name",
                        "Value": "Restored-EC2-Instance"
                    },
                    {
                        "Key": "RestoredFrom",
                        "Value": snapshot_id
                    },
                    {
                        "Key": "RecoveryAMI",
                        "Value": image_id
                    },
                    {
                        "Key": "CreatedBy",
                        "Value": "Lambda-EC2-Restore"
                    },
                    {
                        "Key": "RestoreTimeUTC",
                        "Value": timestamp
                    }
                ]
            },
            {
                "ResourceType": "volume",
                "Tags": [
                    {
                        "Key": "CreatedBy",
                        "Value": "Lambda-EC2-Restore"
                    },
                    {
                        "Key": "RestoredFrom",
                        "Value": snapshot_id
                    }
                ]
            }
        ]
    )

    instance_id = response["Instances"][0]["InstanceId"]

    logger.info(
        "Restored EC2 instance launched successfully. InstanceId: %s",
        instance_id
    )

    return instance_id


def lambda_handler(event, context):
    volume_id = os.environ["SOURCE_VOLUME_ID"]
    root_device_name = os.environ.get(
        "ROOT_DEVICE_NAME",
        "/dev/xvda"
    )
    subnet_id = os.environ["SUBNET_ID"]
    security_group_id = os.environ["SECURITY_GROUP_ID"]
    key_name = os.environ["KEY_NAME"]
    instance_type = os.environ.get("INSTANCE_TYPE", "t3.micro")
    architecture = os.environ.get("ARCHITECTURE", "x86_64")

    try:
        logger.info(
            "Starting EC2 recovery for source volume: %s",
            volume_id
        )

        latest_snapshot = get_latest_snapshot(volume_id)
        snapshot_id = latest_snapshot["SnapshotId"]

        image_id = register_ami(
            snapshot_id,
            root_device_name,
            architecture
        )

        wait_for_ami(image_id)

        instance_id = launch_restored_instance(
            image_id=image_id,
            snapshot_id=snapshot_id,
            subnet_id=subnet_id,
            security_group_id=security_group_id,
            key_name=key_name,
            instance_type=instance_type
        )

        result = {
            "status": "success",
            "source_volume_id": volume_id,
            "latest_snapshot_id": snapshot_id,
            "registered_ami_id": image_id,
            "new_instance_id": instance_id,
            "instance_type": instance_type
        }

        logger.info(
            "EC2 recovery completed: %s",
            json.dumps(result)
        )

        return {
            "statusCode": 200,
            "body": json.dumps(result)
        }

    except ValueError as error:
        logger.exception("Snapshot validation failed.")

        return {
            "statusCode": 404,
            "body": json.dumps(
                {
                    "status": "failed",
                    "error": str(error)
                }
            )
        }

    except WaiterError as error:
        logger.exception("AMI did not become available in time.")

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "failed",
                    "error": str(error)
                }
            )
        }

    except (ClientError, BotoCoreError) as error:
        logger.exception("AWS API operation failed.")

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "failed",
                    "error": str(error)
                }
            )
        }