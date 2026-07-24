import json
import logging
import os
from datetime import date
from decimal import Decimal, InvalidOperation

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger()
logger.setLevel(logging.INFO)

cost_explorer = boto3.client("ce")
sns = boto3.client("sns")


def get_month_date_range():
    """
    Return the Cost Explorer date range for the current month.

    Cost Explorer treats the End date as exclusive, so tomorrow's
    date is used to include today's available cost data.
    """
    today = date.today()
    start_date = today.replace(day=1)

    if today.month == 12:
        next_day = date(today.year + 1, 1, 1)
    else:
        next_day = today.fromordinal(today.toordinal() + 1)

    return start_date.isoformat(), next_day.isoformat()


def lambda_handler(event, context):
    sns_topic_arn = os.environ["SNS_TOPIC_ARN"]
    currency = os.environ.get("CURRENCY", "USD")

    try:
        threshold = Decimal(os.environ.get("COST_THRESHOLD", "50"))
    except InvalidOperation:
        logger.error("COST_THRESHOLD is not a valid number.")

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "failed",
                    "message": "Invalid COST_THRESHOLD value"
                }
            )
        }

    start_date, end_date = get_month_date_range()

    logger.info(
        "Retrieving month-to-date cost from %s to %s",
        start_date,
        end_date
    )

    try:
        response = cost_explorer.get_cost_and_usage(
            TimePeriod={
                "Start": start_date,
                "End": end_date
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"]
        )

        amount_text = (
            response["ResultsByTime"][0]["Total"]
            ["UnblendedCost"]["Amount"]
        )

        current_cost = Decimal(amount_text)

        logger.info(
            "Current month-to-date UnblendedCost: %s %s",
            current_cost,
            currency
        )

        alert_sent = False
        sns_message_id = None

        if current_cost > threshold:
            subject = "AWS Cost Alert: Threshold Exceeded"

            message = (
                "AWS Cost Alert\n\n"
                f"Current month-to-date cost: {currency} {current_cost:.4f}\n"
                f"Configured threshold: {currency} {threshold:.2f}\n"
                f"Period: {start_date} to {end_date}\n\n"
                "Please review active AWS resources in the Billing and "
                "Cost Management console."
            )

            publish_response = sns.publish(
                TopicArn=sns_topic_arn,
                Subject=subject,
                Message=message
            )

            sns_message_id = publish_response["MessageId"]
            alert_sent = True

            logger.info(
                "SNS alert published successfully. MessageId: %s",
                sns_message_id
            )
        else:
            logger.info(
                "Cost is within threshold. No SNS alert was sent."
            )

        result = {
            "status": "success",
            "month_to_date_cost": str(current_cost),
            "currency": currency,
            "threshold": str(threshold),
            "alert_sent": alert_sent,
            "sns_message_id": sns_message_id,
            "period_start": start_date,
            "period_end_exclusive": end_date
        }

        logger.info("Execution result: %s", json.dumps(result))

        return {
            "statusCode": 200,
            "body": json.dumps(result)
        }

    except ClientError as error:
        logger.exception(
            "Failed to retrieve cost data or publish the SNS alert."
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