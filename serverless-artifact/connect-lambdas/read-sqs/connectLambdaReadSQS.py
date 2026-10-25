"""
Copyright 2025 Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Amazon Connect Cases to Salesforce Integration - SQS Message Parser

This Lambda function parses Amazon Connect Cases events from SQS and prepares
data for Salesforce synchronization. It handles case creation, updates, and
comment events while extracting customer profile information.
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

# Initialize AWS clients
profile_client = boto3.client("customer-profiles")
connect_client = boto3.client("connectcases")


def _get_field_string_value(fields_dict: Any, field_name: str) -> str:
    """Safely extract string value from a Cases fields dictionary"""
    if not isinstance(fields_dict, dict):
        return ""
    field = fields_dict.get(field_name)
    if not isinstance(field, dict):
        return ""
    val = field.get("value")
    if isinstance(val, dict):
        return str(val.get("stringValue") or "")
    elif isinstance(val, str):
        return val
    return ""


def _is_performed_by_salesforce(detail: Dict[str, Any]) -> bool:
    """Check if action was performed by Salesforce to prevent infinite event loops"""
    performed_by = detail.get("performedBy")
    if not isinstance(performed_by, dict):
        return False

    # Direct customEntity on performedBy
    if performed_by.get("customEntity") == "salesforce":
        return True

    # Nested customEntity in user
    user = performed_by.get("user")
    if isinstance(user, dict) and user.get("customEntity") == "salesforce":
        return True

    return False


def lambda_handler(event: Any, context: Any) -> Dict[str, Any]:
    """Parse Amazon Connect Cases events and prepare data for Salesforce sync

    Args:
        event: SQS event or Pipe batch containing Connect Cases change notifications
        context: Lambda context object

    Returns:
        Dict containing parsed case data for Salesforce processing
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

        detail = message_body.get("detail", {})
        event_type = detail.get("eventType", "")
        sf_case_field_id = os.environ.get("SF_CASE_FIELD_ID", "")
        profiles_domain = os.environ.get("PROFILES_DOMAIN", "")

        # Extract domain ID from resources list if available
        domain_id = ""
        resources = message_body.get("resources", [])
        if resources and isinstance(resources[0], str):
            domain_id = resources[0].split("/")[-1]

        # Initialize common variables
        amazon_connect_case_id = ""
        summary = ""
        title = ""
        status = ""
        salesforce_case_id = ""
        comments = ""
        phone_number = ""
        sfstatus = "IGNORE"

        is_sf = _is_performed_by_salesforce(detail)

        if event_type == "RELATED_ITEM.CREATED":
            sfstatus = "IGNORE" if is_sf else "COMMENT"

            related_item = detail.get("relatedItem", {})
            amazon_connect_case_id = str(related_item.get("caseId") or "")
            comment_obj = related_item.get("comment", {})
            comments = str(comment_obj.get("body") or "")

            # Retrieve case fields from Connect Cases if domain_id and case_id exist
            if amazon_connect_case_id and domain_id:
                try:
                    case_response = connect_client.get_case(
                        caseId=amazon_connect_case_id,
                        domainId=domain_id,
                        fields=[
                            {"id": "title"},
                            {"id": "summary"},
                            {"id": "status"},
                            {"id": sf_case_field_id},
                        ],
                    )
                    for field in case_response.get("fields", []):
                        fid = field.get("id")
                        val = field.get("value", {})
                        str_val = val.get("stringValue", "") if isinstance(val, dict) else str(val or "")
                        if fid == sf_case_field_id:
                            salesforce_case_id = str_val
                        elif fid == "title":
                            title = str_val
                        elif fid == "summary":
                            summary = str_val
                        elif fid == "status":
                            status = str_val
                except Exception as e:
                    logger.warning(f"Could not retrieve existing case fields for comment: {str(e)}")

        elif event_type == "CASE.UPDATED":
            sfstatus = "IGNORE" if is_sf else "UPDATE"

            case_data = detail.get("case", {})
            amazon_connect_case_id = str(case_data.get("caseId") or "")
            fields_data = case_data.get("fields", {})

            summary = _get_field_string_value(fields_data, "summary")
            title = _get_field_string_value(fields_data, "title")
            status = _get_field_string_value(fields_data, "status")
            salesforce_case_id = _get_field_string_value(fields_data, sf_case_field_id)

            # Get phone number from customer profile if customer_id exists
            customer_arn = _get_field_string_value(fields_data, "customer_id")
            if customer_arn and profiles_domain:
                profile_id = customer_arn.split("/")[-1]
                try:
                    profile_response = profile_client.search_profiles(
                        DomainName=profiles_domain,
                        KeyName="_profileId",
                        Values=[profile_id],
                    )
                    if profile_response.get("Items"):
                        phone_number = str(profile_response["Items"][0].get("PhoneNumber") or "")
                except Exception as e:
                    logger.warning(f"Error retrieving customer profile: {str(e)}")

            # If salesforce_case_id is not in the update payload, fetch it from Connect Cases
            if not salesforce_case_id and amazon_connect_case_id and domain_id and sf_case_field_id:
                try:
                    case_response = connect_client.get_case(
                        caseId=amazon_connect_case_id,
                        domainId=domain_id,
                        fields=[{"id": sf_case_field_id}],
                    )
                    for field in case_response.get("fields", []):
                        if field.get("id") == sf_case_field_id:
                            val = field.get("value", {})
                            salesforce_case_id = val.get("stringValue", "") if isinstance(val, dict) else str(val or "")
                            break
                except Exception as e:
                    logger.warning(f"Could not fetch Salesforce case ID: {str(e)}")

        elif event_type == "CASE.CREATED":
            # If created by Salesforce, send UPDATE back to SF to link the AmazonConnectCaseID!
            # If created in Connect Agent Workspace, send CREATE to SF to create the new SF case.
            sfstatus = "UPDATE" if is_sf else "CREATE"

            case_data = detail.get("case", {})
            amazon_connect_case_id = str(case_data.get("caseId") or "")
            fields_data = case_data.get("fields", {})

            summary = _get_field_string_value(fields_data, "summary")
            title = _get_field_string_value(fields_data, "title")
            status = _get_field_string_value(fields_data, "status")
            salesforce_case_id = _get_field_string_value(fields_data, sf_case_field_id)

            # Get phone number from customer profile if customer_id exists
            customer_arn = _get_field_string_value(fields_data, "customer_id")
            if customer_arn and profiles_domain:
                profile_id = customer_arn.split("/")[-1]
                try:
                    profile_response = profile_client.search_profiles(
                        DomainName=profiles_domain,
                        KeyName="_profileId",
                        Values=[profile_id],
                    )
                    if profile_response.get("Items"):
                        phone_number = str(profile_response["Items"][0].get("PhoneNumber") or "")
                except Exception as e:
                    logger.warning(f"Error retrieving customer profile: {str(e)}")

        else:
            logger.info(f"Unhandled or unknown eventType: '{event_type}', marking as IGNORE")
            sfstatus = "IGNORE"

        logger.info(
            f"Connect event parsed: eventType='{event_type}', sfStatus='{sfstatus}', "
            f"AmazonConnectCaseID='{amazon_connect_case_id}', SalesforceCaseID='{salesforce_case_id}'"
        )

        return {
            "statusCode": 200,
            "sfStatus": sfstatus,
            "AmazonConnectCaseID": amazon_connect_case_id,
            "Summary": summary,
            "Title": title,
            "Status": status,
            "Comments": comments,
            "SalesforceCaseID": salesforce_case_id,
            "EmailAddress": "",
            "PhoneNumber": phone_number,
        }

    except Exception as e:
        logger.error(f"Error processing Connect Cases event: {str(e)}", exc_info=True)
        raise
