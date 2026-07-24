import json
import logging
import os

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sns = boto3.client("sns")

PUBLIC_ACL_URIS = {
    "http://acs.amazonaws.com/groups/global/AllUsers":
        "AllUsers",
    "http://acs.amazonaws.com/groups/global/AuthenticatedUsers":
        "AuthenticatedUsers"
}


def check_public_access_block(bucket_name):
    """
    Check whether all four bucket-level Block Public Access settings
    are enabled.

    A missing configuration is treated as non-compliant because the
    bucket does not have complete bucket-level protection.
    """
    try:
        response = s3.get_public_access_block(Bucket=bucket_name)
        configuration = response["PublicAccessBlockConfiguration"]

        settings = {
            "BlockPublicAcls": configuration.get(
                "BlockPublicAcls",
                False
            ),
            "IgnorePublicAcls": configuration.get(
                "IgnorePublicAcls",
                False
            ),
            "BlockPublicPolicy": configuration.get(
                "BlockPublicPolicy",
                False
            ),
            "RestrictPublicBuckets": configuration.get(
                "RestrictPublicBuckets",
                False
            )
        }

        disabled_settings = [
            name
            for name, enabled in settings.items()
            if not enabled
        ]

        return {
            "all_enabled": not disabled_settings,
            "disabled_settings": disabled_settings,
            "configuration_missing": False
        }

    except ClientError as error:
        error_code = error.response["Error"]["Code"]

        if error_code in {
            "NoSuchPublicAccessBlockConfiguration",
            "NoSuchPublicAccessBlock"
        }:
            return {
                "all_enabled": False,
                "disabled_settings": [
                    "BlockPublicAcls",
                    "IgnorePublicAcls",
                    "BlockPublicPolicy",
                    "RestrictPublicBuckets"
                ],
                "configuration_missing": True
            }

        raise


def check_bucket_policy(bucket_name):
    """
    Ask S3 whether the bucket policy is considered public.
    """
    try:
        response = s3.get_bucket_policy_status(
            Bucket=bucket_name
        )

        return response.get(
            "PolicyStatus",
            {}
        ).get("IsPublic", False)

    except ClientError as error:
        error_code = error.response["Error"]["Code"]

        if error_code in {
            "NoSuchBucketPolicy",
            "NoSuchPolicy",
            "404"
        }:
            return False

        raise


def check_bucket_acl(bucket_name):
    """
    Inspect the bucket ACL for grants to AllUsers or
    AuthenticatedUsers.
    """
    response = s3.get_bucket_acl(Bucket=bucket_name)

    public_grants = []

    for grant in response.get("Grants", []):
        grantee = grant.get("Grantee", {})
        uri = grantee.get("URI")

        if uri in PUBLIC_ACL_URIS:
            public_grants.append(
                {
                    "group": PUBLIC_ACL_URIS[uri],
                    "permission": grant.get(
                        "Permission",
                        "UNKNOWN"
                    )
                }
            )

    return public_grants


def audit_bucket(bucket_name):
    """
    Audit one bucket and return its security findings.
    """
    logger.info("Auditing bucket: %s", bucket_name)

    block_status = check_public_access_block(bucket_name)
    policy_is_public = check_bucket_policy(bucket_name)
    public_acl_grants = check_bucket_acl(bucket_name)

    reasons = []

    if not block_status["all_enabled"]:
        if block_status["configuration_missing"]:
            reasons.append(
                "Bucket-level Block Public Access configuration "
                "is missing"
            )
        else:
            disabled = ", ".join(
                block_status["disabled_settings"]
            )
            reasons.append(
                f"Block Public Access settings disabled: {disabled}"
            )

    if policy_is_public:
        reasons.append(
            "Bucket policy is classified as public by Amazon S3"
        )

    if public_acl_grants:
        acl_description = ", ".join(
            f"{grant['group']}={grant['permission']}"
            for grant in public_acl_grants
        )
        reasons.append(
            f"Public ACL grants detected: {acl_description}"
        )

    result = {
        "bucket_name": bucket_name,
        "non_compliant": bool(reasons),
        "policy_is_public": policy_is_public,
        "public_acl_grants": public_acl_grants,
        "block_public_access": block_status,
        "reasons": reasons
    }

    logger.info(
        "Bucket audit result: %s",
        json.dumps(result)
    )

    return result


def build_alert_message(non_compliant_buckets, total_buckets):
    """
    Build one consolidated SNS notification.
    """
    lines = [
        "AWS S3 Public Access Audit Alert",
        "",
        f"Buckets audited: {total_buckets}",
        f"Non-compliant buckets: "
        f"{len(non_compliant_buckets)}",
        ""
    ]

    for number, bucket in enumerate(
        non_compliant_buckets,
        start=1
    ):
        lines.append(
            f"{number}. Bucket: {bucket['bucket_name']}"
        )

        for reason in bucket["reasons"]:
            lines.append(f"   - {reason}")

        lines.append("")

    lines.extend(
        [
            "Review these buckets immediately and confirm whether "
            "the configuration is intentional.",
            "",
            "Recommended action: enable all four S3 Block Public "
            "Access settings unless public access is explicitly "
            "required and formally approved."
        ]
    )

    return "\n".join(lines)


def lambda_handler(event, context):
    sns_topic_arn = os.environ["SNS_TOPIC_ARN"]

    try:
        list_response = s3.list_buckets()
        buckets = list_response.get("Buckets", [])

        logger.info(
            "Starting S3 audit. Total buckets found: %s",
            len(buckets)
        )

        audit_results = []
        audit_errors = []

        for bucket in buckets:
            bucket_name = bucket["Name"]

            try:
                audit_results.append(
                    audit_bucket(bucket_name)
                )

            except ClientError as error:
                error_message = (
                    f"Unable to fully audit bucket "
                    f"{bucket_name}: {error}"
                )

                logger.exception(error_message)

                audit_errors.append(
                    {
                        "bucket_name": bucket_name,
                        "error": str(error)
                    }
                )

        non_compliant_buckets = [
            result
            for result in audit_results
            if result["non_compliant"]
        ]

        alert_sent = False
        sns_message_id = None

        if non_compliant_buckets:
            message = build_alert_message(
                non_compliant_buckets,
                len(buckets)
            )

            publish_response = sns.publish(
                TopicArn=sns_topic_arn,
                Subject="AWS Security Alert: S3 Public Access Audit",
                Message=message
            )

            sns_message_id = publish_response["MessageId"]
            alert_sent = True

            logger.warning(
                "SNS security alert sent. MessageId: %s",
                sns_message_id
            )
        else:
            logger.info(
                "No non-compliant S3 buckets were detected."
            )

        result = {
            "status": "success",
            "total_buckets": len(buckets),
            "successfully_audited": len(audit_results),
            "non_compliant_count": len(
                non_compliant_buckets
            ),
            "non_compliant_buckets": [
                bucket["bucket_name"]
                for bucket in non_compliant_buckets
            ],
            "audit_error_count": len(audit_errors),
            "audit_errors": audit_errors,
            "alert_sent": alert_sent,
            "sns_message_id": sns_message_id
        }

        logger.info(
            "S3 audit completed: %s",
            json.dumps(result)
        )

        return {
            "statusCode": 200,
            "body": json.dumps(result)
        }

    except ClientError as error:
        logger.exception(
            "The S3 public-access audit failed."
        )

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "failed",
                    "error": str(error)
                }
            )
        }