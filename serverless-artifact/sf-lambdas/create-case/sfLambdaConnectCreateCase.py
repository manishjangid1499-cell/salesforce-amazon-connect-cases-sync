"""
Copyright 2025 Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Salesforce to Amazon Connect Integration - Case Creator

This Lambda function creates new cases in Amazon Connect Cases based on
Salesforce case data. It handles domain and template lookup, case creation,
field mapping, and initial comment creation.
"""

import json
import logging
import os
import random
import string
import boto3
from typing import Dict, Any

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

# Constants
DEFAULT_CLIENT_TOKEN_LENGTH = 8
DEFAULT_CONTENT_TYPE = "Text/Plain"

# Initialize AWS clients
client = boto3.client("connectcases")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Create a new case in Amazon Connect Cases from Salesforce data

    Args:
        event: Event containing case and profile information
        context: Lambda context object

    Returns:
        Dict containing status code and created case ID
    """

    try:
        # Extract environment variables
        sf_case_field_id = os.environ["SF_CASE_FIELD_ID"]
        domain_name = os.environ["DOMAIN_NAME"]
        profiles_domain = os.environ["PROFILES_DOMAIN"]
        template_name = os.environ["TEMPLATE_NAME"]
        profiles_sub = os.environ["PROFILES_SUB"]
        content_type = os.environ.get("COMMENT_CONTENT_TYPE", DEFAULT_CONTENT_TYPE)

        # Extract event data safely
        profile_id = str(event.get("ProfileID") or "")
        subject = str(event.get("Subject") or "Case from Salesforce")
        description = str(event.get("Description") or "")
        comments = str(event.get("Comments") or "")
        salesforce_case_id = str(event.get("SalesforceCaseID") or "")

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

        # Find template ID by name (with pagination support)
        template_id = ""
        paginator_t = client.get_paginator("list_templates")
        for page in paginator_t.paginate(domainId=domain_id, status=["Active"]):
            for template in page.get("templates", []):
                if template.get("name") == template_name:
                    template_id = template["templateId"]
                    break
            if template_id:
                break

        if not template_id:
            raise ValueError(f"Template '{template_name}' not found")

        # Generate client token for idempotency
        token_length = int(
            os.environ.get("CLIENT_TOKEN_LENGTH", DEFAULT_CLIENT_TOKEN_LENGTH)
        )
        client_token = _generate_client_token(token_length)

        # Build case fields dynamically
        fields = [
            {"id": "title", "value": {"stringValue": subject}},
            {"id": "summary", "value": {"stringValue": description}},
        ]

        if profile_id:
            profile_arn = f"{profiles_sub}{profiles_domain}/profiles/{profile_id}"
            fields.append({"id": "customer_id", "value": {"stringValue": profile_arn}})

        if salesforce_case_id and sf_case_field_id:
            fields.append({"id": sf_case_field_id, "value": {"stringValue": salesforce_case_id}})

        # Create the case
        response = client.create_case(
            clientToken=client_token,
            domainId=domain_id,
            fields=fields,
            performedBy={"customEntity": "salesforce"},
            templateId=template_id,
        )

        case_id = response.get("caseId", "")
        logger.info(f"Successfully created case: {case_id}")

        # Add initial comment if provided
        if comments and case_id:
            try:
                client.create_related_item(
                    domainId=domain_id,
                    caseId=case_id,
                    content={"comment": {"body": comments, "contentType": content_type}},
                    performedBy={"customEntity": "salesforce"},
                    type="Comment",
                )
                logger.info(f"Successfully added initial comment to case: {case_id}")
            except Exception as ce:
                logger.warning(f"Could not add initial comment to case {case_id}: {ce}")

        return {"statusCode": 200, "caseId": case_id}

    except Exception as e:
        logger.error(f"Error creating case: {str(e)}", exc_info=True)
        raise


def _generate_client_token(length: int) -> str:
    """Generate a random client token for idempotency

    Args:
        length: Length of the token to generate

    Returns:
        Random string token
    """
    return "".join(
        random.choice(string.ascii_lowercase) for _ in range(length)
    )  # nosec B311
