"""
Copyright 2025 Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Salesforce to Amazon Connect Integration - Case Updater

This Lambda function updates existing cases in Amazon Connect Cases based on
Salesforce case updates. It handles case field updates and comment creation.
"""

import json
import logging
import os
import boto3
from typing import Dict, Any

# Constants
DEFAULT_CONTENT_TYPE = "Text/Plain"

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

# Initialize AWS clients
client = boto3.client("connectcases")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Update an existing case in Amazon Connect Cases from Salesforce data

    Args:
        event: Event containing case update information
        context: Lambda context object

    Returns:
        Dict containing status code and updated case ID
    """

    try:
        # Extract environment variables
        domain_name = os.environ["DOMAIN_NAME"]
        sf_case_field_id = os.environ["SF_CASE_FIELD_ID"]
        content_type = os.environ.get("COMMENT_CONTENT_TYPE", DEFAULT_CONTENT_TYPE)

        # Extract event data safely
        amazon_connect_case_id = str(event.get("AmazonConnectCaseID") or "")
        description = str(event.get("Description") or "")
        subject = str(event.get("Subject") or "")
        comments = str(event.get("Comments") or "")
        salesforce_case_id = str(event.get("SalesforceCaseID") or "")

        if not amazon_connect_case_id:
            raise ValueError("AmazonConnectCaseID is required for case update")

        logger.info(f"Updating case: {amazon_connect_case_id}")

        # Find domain ID by name (with pagination support)
        domain_id = ""
        paginator = client.get_paginator("list_domains")
        for page in paginator.paginate():
            for domain in page.get("domains", []):
                if domain.get("name") == domain_name:
                    domain_id = domain["domainId"]
                    break
            if domain_id:
                break

        if not domain_id:
            raise ValueError(f"Domain '{domain_name}' not found")

        # Build fields to update dynamically so blank fields don't overwrite existing data
        fields_to_update = []
        if subject:
            fields_to_update.append({"id": "title", "value": {"stringValue": subject}})
        if description:
            fields_to_update.append({"id": "summary", "value": {"stringValue": description}})
        if salesforce_case_id and sf_case_field_id:
            fields_to_update.append({"id": sf_case_field_id, "value": {"stringValue": salesforce_case_id}})

        if fields_to_update:
            logger.debug(f"Updating case fields: {fields_to_update}")
            client.update_case(
                domainId=domain_id,
                caseId=amazon_connect_case_id,
                fields=fields_to_update,
                performedBy={"customEntity": "salesforce"},
            )
            logger.info("Case fields updated successfully")

        # Add comment if provided
        if comments:
            logger.debug("Adding comment to case")
            client.create_related_item(
                domainId=domain_id,
                caseId=amazon_connect_case_id,
                content={"comment": {"body": comments, "contentType": content_type}},
                performedBy={"customEntity": "salesforce"},
                type="Comment",
            )
            logger.info("Comment added successfully")

        return {"statusCode": 200, "caseId": amazon_connect_case_id}

    except Exception as e:
        logger.error(f"Error updating case: {str(e)}", exc_info=True)
        raise
