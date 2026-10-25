"""
Copyright 2025 Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Salesforce to Amazon Connect Integration - SQS Message Parser

This Lambda function parses Salesforce platform events from SQS and extracts
case information for Amazon Connect Cases synchronization.
"""

import json
import logging
import os
from typing import Dict, Any

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)


def lambda_handler(event: Any, context: Any) -> Dict[str, Any]:
    """Parse Salesforce platform events and extract case data

    Args:
        event: SQS event or Pipe batch containing Salesforce platform event
        context: Lambda context object

    Returns:
        Dict containing extracted case information
    """

    try:
        # Extract record from list (EventBridge Pipe batch), dict, or SQS Records
        if isinstance(event, list) and len(event) > 0:
            record = event[0]
        elif isinstance(event, dict) and "Records" in event and len(event["Records"]) > 0:
            record = event["Records"][0]
        elif isinstance(event, dict):
            record = event
        else:
            raise ValueError(f"Unsupported event structure: {type(event)}")

        # Extract and parse message body
        if isinstance(record, dict) and "body" in record:
            raw_body = record["body"]
            message_body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
        else:
            message_body = record

        # Extract payload from EventBridge envelope or directly
        if isinstance(message_body, dict) and "detail" in message_body:
            detail = message_body["detail"]
            payload = detail.get("payload", detail)
        else:
            payload = message_body

        if not isinstance(payload, dict):
            raise ValueError("Parsed payload is not a dictionary")

        # Extract case information from Salesforce payload, ensuring safe string defaults
        amazon_connect_case_id = str(payload.get("AmazonConnectCaseID__c") or "")
        description = str(payload.get("Description__c") or "")
        comments = str(payload.get("Case_Comments__c") or "")
        phone_number = str(payload.get("Phone_Number__c") or "")
        salesforce_case_id = str(payload.get("CaseID__c") or "")
        subject = str(payload.get("Subject__c") or "")

        logger.info(
            f"Successfully parsed SF event. SalesforceCaseID: '{salesforce_case_id}', "
            f"AmazonConnectCaseID: '{amazon_connect_case_id}', Subject: '{subject}'"
        )

        return {
            "statusCode": 200,
            "body": "",
            "AmazonConnectCaseID": amazon_connect_case_id,
            "Description": description,
            "Subject": subject,
            "Comments": comments,
            "PhoneNumber": phone_number,
            "SalesforceCaseID": salesforce_case_id,
        }

    except Exception as e:
        logger.error(f"Unexpected error processing event: {str(e)}", exc_info=True)
        raise
