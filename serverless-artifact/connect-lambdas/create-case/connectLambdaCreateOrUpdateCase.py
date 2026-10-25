"""
Copyright 2025 Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Amazon Connect Cases to Salesforce Integration - Case Creator

This Lambda function creates or updates Salesforce cases via EventBridge
based on Amazon Connect Cases events. It determines the operation type
and sends formatted events to Salesforce.
"""

import json
import logging
import os
import boto3
from typing import Dict, Any

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

# Constants
DEFAULT_CASE_ORIGIN = "Phone"
DEFAULT_CASE_STATUS = "New"

# Initialize AWS clients
eventbridge_client = boto3.client("events")


def _sanitize_string(val: Any) -> str:
    """Sanitize string values to ensure valid JSON representation in EventBridge templates"""
    if val is None:
        return ""
    s = str(val).strip()
    # Normalize control characters that could break EventBridge input transformer JSON
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace('"', "'")
    return s


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Create or update Salesforce case via EventBridge

    Args:
        event: Case data from Connect Cases processing
        context: Lambda context object

    Returns:
        Dict containing status code and response body
    """

    try:
        # Extract case data from event safely
        amazon_connect_case_id = _sanitize_string(event.get("AmazonConnectCaseID", ""))
        summary = _sanitize_string(event.get("Summary", ""))
        title = _sanitize_string(event.get("Title", ""))
        status = _sanitize_string(event.get("Status", ""))
        salesforce_case_id = _sanitize_string(event.get("SalesforceCaseID", ""))
        comments = _sanitize_string(event.get("Comments", ""))
        phone_number = _sanitize_string(event.get("PhoneNumber", ""))

        # Get operation type from event status
        sf_operation = str(event.get("sfStatus", "UPDATE")).upper()

        # Get configurable values
        case_origin = os.environ.get("CASE_ORIGIN", DEFAULT_CASE_ORIGIN)
        case_status = os.environ.get("CASE_STATUS", DEFAULT_CASE_STATUS)

        # Prepare payload for Salesforce
        input_params = {
            "sf_operation": sf_operation,
            "Origin": case_origin,
            "Status": status if status else case_status,
            "Subject": title,
            "Description": summary,
            "AmazonConnectCaseID": amazon_connect_case_id,
            "Comments": comments,
            "SalesforceCaseID": salesforce_case_id,
            "PhoneNumber": phone_number,
        }

        event_bus_name = os.environ["EVENT_BUS_NAME"]

        # Send event to EventBridge for Salesforce processing
        response = eventbridge_client.put_events(
            Entries=[
                {
                    "Source": "case.event",
                    "DetailType": "Case Change Event",
                    "Detail": json.dumps(input_params),
                    "EventBusName": event_bus_name,
                }
            ]
        )

        failed_entry_count = response.get("FailedEntryCount", 0)
        if failed_entry_count > 0:
            error_msg = f"Failed to deliver event to EventBridge: {response.get('Entries')}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        status_code = response["ResponseMetadata"]["HTTPStatusCode"]
        logger.info(
            f"Successfully sent event to EventBridge ({event_bus_name}) with operation: {sf_operation}. "
            f"ConnectCase: {amazon_connect_case_id}, SFCase: {salesforce_case_id}"
        )

        return {
            "statusCode": status_code,
            "body": json.dumps({"message": "Event sent successfully"}),
        }

    except Exception as e:
        logger.error(f"Error sending event to EventBridge: {str(e)}", exc_info=True)
        raise
