"""
Copyright 2025 Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Salesforce to Amazon Connect Integration - Customer Profile Finder

This Lambda function searches for customer profiles in Amazon Connect
Customer Profiles by phone number or email address. If no profile exists,
it creates a new one.

Author: AWS Professional Services
Version: 1.0
"""

import json
import logging
import os
import re
import boto3
from typing import Dict, Any
from botocore.exceptions import ClientError

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

# Constants
PHONE_KEY_NAME = "_phone"
EMAIL_KEY_NAME = "_email"
DEFAULT_MAX_SEARCH_RESULTS = 100
DEFAULT_COUNTRY_CODE = "+1"

# Initialize AWS clients
client = boto3.client("customer-profiles")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Find or create customer profile in Amazon Connect Customer Profiles

    Args:
        event: Event containing customer contact information
        context: Lambda context object

    Returns:
        Dict containing profile ID and case information
    """

    try:
        domain_name = os.environ["DOMAIN_NAME"]
        max_results = int(
            os.environ.get("MAX_SEARCH_RESULTS", DEFAULT_MAX_SEARCH_RESULTS)
        )
        email = str(event.get("EmailAddress") or "").strip()
        raw_phone = event.get("PhoneNumber")
        phone_number = format_phone_number(raw_phone)

        profile_id = ""

        # Search by phone first if available
        if phone_number:
            country_code = os.environ.get("COUNTRY_CODE", DEFAULT_COUNTRY_CODE)
            formatted_phone = f"{country_code}{phone_number}"
            profile_id = _find_or_create_profile_by_phone(
                domain_name, formatted_phone, max_results
            )

        # Search by email if no phone number provided
        elif email:
            profile_id = _find_or_create_profile_by_email(
                domain_name, email, max_results
            )

        logger.info(f"Resolved Customer Profile ID: '{profile_id}'")

        return {
            "statusCode": 200,
            "ProfileID": profile_id,
            "AmazonConnectCaseID": str(event.get("AmazonConnectCaseID") or ""),
            "Description": str(event.get("Description") or ""),
            "Subject": str(event.get("Subject") or ""),
            "Comments": str(event.get("Comments") or ""),
            "SalesforceCaseID": str(event.get("SalesforceCaseID") or ""),
        }

    except ClientError as e:
        logger.error(f"AWS service error: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise


def format_phone_number(phone: Any) -> str:
    """Format phone number to 10-digit format

    Args:
        phone: Input phone number in any format

    Returns:
        Formatted 10-digit phone number or empty string
    """
    if not phone or not isinstance(phone, str):
        return ""

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone)

    # Return last 10 digits if more than 10, otherwise return as is
    return digits[-10:] if len(digits) >= 10 else digits


def _find_or_create_profile_by_phone(
    domain_name: str, phone_number: str, max_results: int
) -> str:
    """Find or create profile by phone number

    Args:
        domain_name: Customer Profiles domain name
        phone_number: Formatted phone number with country code
        max_results: Maximum number of search results

    Returns:
        Profile ID
    """
    try:
        response = client.search_profiles(
            MaxResults=max_results,
            DomainName=domain_name,
            KeyName=PHONE_KEY_NAME,
            Values=[phone_number],
        )

        if response.get("Items"):
            return response["Items"][0]["ProfileId"]
        else:
            # Create new profile with phone number
            response = client.create_profile(
                DomainName=domain_name, PhoneNumber=phone_number
            )
            return response["ProfileId"]

    except ClientError as e:
        logger.error(f"AWS service error finding/creating profile by phone: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error finding/creating profile by phone: {str(e)}")
        raise


def _find_or_create_profile_by_email(
    domain_name: str, email: str, max_results: int
) -> str:
    """Find or create profile by email address

    Args:
        domain_name: Customer Profiles domain name
        email: Email address
        max_results: Maximum number of search results

    Returns:
        Profile ID
    """
    try:
        response = client.search_profiles(
            MaxResults=max_results,
            DomainName=domain_name,
            KeyName=EMAIL_KEY_NAME,
            Values=[email],
        )

        if response.get("Items"):
            return response["Items"][0]["ProfileId"]
        else:
            # Create new profile with email
            response = client.create_profile(DomainName=domain_name, EmailAddress=email)
            return response["ProfileId"]

    except ClientError as e:
        logger.error(f"AWS service error finding/creating profile by email: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error finding/creating profile by email: {str(e)}")
        raise
