"""
Shippo Shipment Extras Discovery Test Suite

This test suite empirically determines which extras are supported by each carrier
and service level combination in the Shippo API.

Strategy:
1. Get all carrier accounts connected to your Shippo account
2. For each carrier, get available service levels
3. For each carrier/service level combo, test each extra by attempting to create a shipment
4. Analyze error responses to determine support vs. rejection

Usage:
    export SHIPPO_API_KEY="your_api_key_here"
    python test_shippo_extras.py

    # Or run specific tests
    python test_shippo_extras.py --carrier usps
    python test_shippo_extras.py --carrier fedex --service-level fedex_ground
    python test_shippo_extras.py --extra signature_confirmation
"""

import os
import json
import time
import argparse
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum
import requests


# =============================================================================
# Configuration
# =============================================================================

SHIPPO_API_BASE = "https://api.goshippo.com"

# Test addresses (valid US addresses for domestic testing)
TEST_ADDRESS_FROM = {
    "name": "Test Sender",
    "street1": "215 Clayton St",
    "city": "San Francisco",
    "state": "CA",
    "zip": "94117",
    "country": "US",
    "phone": "415-555-1234",
    "email": "sender@test.com"
}

TEST_ADDRESS_TO = {
    "name": "Test Recipient",
    "street1": "1600 Pennsylvania Avenue NW",
    "city": "Washington",
    "state": "DC",
    "zip": "20500",
    "country": "US",
    "phone": "202-555-1234",
    "email": "recipient@test.com"
}

# International test address (for customs testing)
TEST_ADDRESS_INTERNATIONAL = {
    "name": "International Recipient",
    "street1": "10 Downing Street",
    "city": "London",
    "state": "",
    "zip": "SW1A 2AA",
    "country": "GB",
    "phone": "+44-20-7925-0918",
    "email": "intl@test.com"
}

# Standard test parcel
TEST_PARCEL = {
    "length": "10",
    "width": "8",
    "height": "6",
    "distance_unit": "in",
    "weight": "2",
    "mass_unit": "lb"
}


# =============================================================================
# Extra Definitions - All known extras from Shippo API schema
# =============================================================================

class ExtraCategory(Enum):
    DELIVERY = "delivery"
    BILLING = "billing"
    INSURANCE = "insurance"
    REFERENCE = "reference"
    HAZMAT = "hazmat"
    SIGNATURE = "signature"
    RETURN = "return"
    CARRIER_SPECIFIC = "carrier_specific"


@dataclass
class ExtraDefinition:
    """Defines an extra and how to test it"""
    name: str
    category: ExtraCategory
    test_value: Any
    description: str
    documented_carriers: list[str] = field(default_factory=list)
    requires_international: bool = False
    requires_specific_carrier: Optional[str] = None


# Complete list of extras to test
EXTRAS_TO_TEST: list[ExtraDefinition] = [
    # Signature options
    ExtraDefinition(
        name="signature_confirmation",
        category=ExtraCategory.SIGNATURE,
        test_value="STANDARD",
        description="Standard signature confirmation",
        documented_carriers=["usps", "fedex", "ups"]
    ),
    ExtraDefinition(
        name="signature_confirmation_adult",
        category=ExtraCategory.SIGNATURE,
        test_value="ADULT",
        description="Adult signature confirmation",
        documented_carriers=["usps", "fedex", "ups"]
    ),
    ExtraDefinition(
        name="signature_confirmation_certified",
        category=ExtraCategory.SIGNATURE,
        test_value="CERTIFIED",
        description="Certified mail signature (USPS)",
        documented_carriers=["usps"]
    ),
    ExtraDefinition(
        name="signature_confirmation_indirect",
        category=ExtraCategory.SIGNATURE,
        test_value="INDIRECT",
        description="Indirect signature (FedEx)",
        documented_carriers=["fedex"]
    ),
    ExtraDefinition(
        name="signature_confirmation_carrier",
        category=ExtraCategory.SIGNATURE,
        test_value="CARRIER_CONFIRMATION",
        description="Carrier confirmation (Deutsche Post)",
        documented_carriers=["deutsche_post"]
    ),

    # Insurance
    ExtraDefinition(
        name="insurance_shippo",
        category=ExtraCategory.INSURANCE,
        test_value={"amount": "100", "currency": "USD", "content": "Test goods"},
        description="Shippo/XCover insurance"
    ),
    ExtraDefinition(
        name="insurance_fedex",
        category=ExtraCategory.INSURANCE,
        test_value={"amount": "100", "currency": "USD", "content": "Test goods", "provider": "FEDEX"},
        description="FedEx carrier insurance",
        documented_carriers=["fedex"]
    ),
    ExtraDefinition(
        name="insurance_ups",
        category=ExtraCategory.INSURANCE,
        test_value={"amount": "100", "currency": "USD", "content": "Test goods", "provider": "UPS"},
        description="UPS carrier insurance",
        documented_carriers=["ups"]
    ),
    ExtraDefinition(
        name="insurance_ontrac",
        category=ExtraCategory.INSURANCE,
        test_value={"amount": "100", "currency": "USD", "content": "Test goods", "provider": "ONTRAC"},
        description="OnTrac carrier insurance",
        documented_carriers=["ontrac"]
    ),

    # COD
    ExtraDefinition(
        name="cod_any",
        category=ExtraCategory.DELIVERY,
        test_value={"amount": "50.00", "currency": "USD", "payment_method": "ANY"},
        description="COD with any payment method",
        documented_carriers=["ups"]
    ),
    ExtraDefinition(
        name="cod_cash",
        category=ExtraCategory.DELIVERY,
        test_value={"amount": "50.00", "currency": "USD", "payment_method": "CASH"},
        description="COD with cash only",
        documented_carriers=["ups"]
    ),
    ExtraDefinition(
        name="cod_secured",
        category=ExtraCategory.DELIVERY,
        test_value={"amount": "50.00", "currency": "USD", "payment_method": "SECURED_FUNDS"},
        description="COD with secured funds",
        documented_carriers=["ups"]
    ),

    # Billing
    ExtraDefinition(
        name="billing_recipient",
        category=ExtraCategory.BILLING,
        test_value={"type": "RECIPIENT"},
        description="Bill recipient for shipping",
        documented_carriers=["ups", "fedex", "dhl_germany"]
    ),
    ExtraDefinition(
        name="billing_third_party",
        category=ExtraCategory.BILLING,
        test_value={"type": "THIRD_PARTY", "account": "123456", "zip": "94117", "country": "US"},
        description="Bill third party for shipping",
        documented_carriers=["ups", "fedex", "dhl_germany"]
    ),
    ExtraDefinition(
        name="billing_collect",
        category=ExtraCategory.BILLING,
        test_value={"type": "COLLECT"},
        description="Collect billing",
        documented_carriers=["ups", "fedex"]
    ),

    # Alcohol
    ExtraDefinition(
        name="alcohol_consumer",
        category=ExtraCategory.HAZMAT,
        test_value={"contains_alcohol": True, "recipient_type": "consumer"},
        description="Alcohol shipment to consumer",
        documented_carriers=["fedex", "ups"]
    ),
    ExtraDefinition(
        name="alcohol_licensee",
        category=ExtraCategory.HAZMAT,
        test_value={"contains_alcohol": True, "recipient_type": "licensee"},
        description="Alcohol shipment to licensee",
        documented_carriers=["fedex", "ups"]
    ),

    # Dry Ice
    ExtraDefinition(
        name="dry_ice",
        category=ExtraCategory.HAZMAT,
        test_value={"contains_dry_ice": True, "weight": "5"},
        description="Dry ice shipment",
        documented_carriers=["fedex", "veho", "ups"]
    ),

    # Dangerous Goods (USPS)
    ExtraDefinition(
        name="dangerous_goods",
        category=ExtraCategory.HAZMAT,
        test_value={"contains": True},
        description="Contains dangerous goods",
        documented_carriers=["usps"]
    ),
    ExtraDefinition(
        name="dangerous_goods_lithium",
        category=ExtraCategory.HAZMAT,
        test_value={"lithium_batteries": {"contains": True}},
        description="Contains lithium batteries",
        documented_carriers=["usps"]
    ),
    ExtraDefinition(
        name="dangerous_goods_biological",
        category=ExtraCategory.HAZMAT,
        test_value={"biological_material": {"contains": True}},
        description="Contains biological material",
        documented_carriers=["usps"]
    ),

    # Dangerous Goods Code (DHL eCommerce)
    ExtraDefinition(
        name="dangerous_goods_code_01",
        category=ExtraCategory.HAZMAT,
        test_value="01",
        description="DHL eCommerce dangerous goods code 01",
        documented_carriers=["dhl_ecommerce"],
        requires_specific_carrier="dhl_ecommerce"
    ),

    # Delivery options
    ExtraDefinition(
        name="saturday_delivery",
        category=ExtraCategory.DELIVERY,
        test_value=True,
        description="Saturday delivery"
    ),
    ExtraDefinition(
        name="authority_to_leave",
        category=ExtraCategory.DELIVERY,
        test_value=True,
        description="Authority to leave without signature"
    ),
    ExtraDefinition(
        name="delivery_instructions",
        category=ExtraCategory.DELIVERY,
        test_value="Leave at back door",
        description="Delivery instructions"
    ),
    ExtraDefinition(
        name="carbon_neutral",
        category=ExtraCategory.DELIVERY,
        test_value=True,
        description="Carbon neutral shipping"
    ),
    ExtraDefinition(
        name="premium",
        category=ExtraCategory.DELIVERY,
        test_value=True,
        description="Premium service"
    ),

    # Reference fields
    ExtraDefinition(
        name="reference_1",
        category=ExtraCategory.REFERENCE,
        test_value="REF-001",
        description="Reference field 1"
    ),
    ExtraDefinition(
        name="reference_2",
        category=ExtraCategory.REFERENCE,
        test_value="REF-002",
        description="Reference field 2"
    ),
    ExtraDefinition(
        name="customer_reference",
        category=ExtraCategory.REFERENCE,
        test_value={"value": "CUST-REF-001"},
        description="Customer reference on label",
        documented_carriers=["fedex", "ups"]
    ),
    ExtraDefinition(
        name="po_number",
        category=ExtraCategory.REFERENCE,
        test_value={"value": "PO-12345"},
        description="PO number on label",
        documented_carriers=["fedex", "ups"]
    ),
    ExtraDefinition(
        name="invoice_number",
        category=ExtraCategory.REFERENCE,
        test_value={"value": "INV-12345"},
        description="Invoice number on label",
        documented_carriers=["fedex", "ups"]
    ),
    ExtraDefinition(
        name="dept_number",
        category=ExtraCategory.REFERENCE,
        test_value={"value": "DEPT-001"},
        description="Department number on label",
        documented_carriers=["fedex", "ups"]
    ),
    ExtraDefinition(
        name="rma_number",
        category=ExtraCategory.REFERENCE,
        test_value={"value": "RMA-12345"},
        description="RMA number on label",
        documented_carriers=["fedex", "ups"]
    ),

    # Return options
    ExtraDefinition(
        name="is_return",
        category=ExtraCategory.RETURN,
        test_value=True,
        description="Return shipment"
    ),
    ExtraDefinition(
        name="return_service_print_and_mail",
        category=ExtraCategory.RETURN,
        test_value="PRINT_AND_MAIL",
        description="Return service - print and mail"
    ),
    ExtraDefinition(
        name="return_service_electronic",
        category=ExtraCategory.RETURN,
        test_value="ELECTRONIC_LABEL",
        description="Return service - electronic label"
    ),

    # QR Code
    ExtraDefinition(
        name="qr_code_requested",
        category=ExtraCategory.DELIVERY,
        test_value=True,
        description="Request QR code for label"
    ),

    # Bypass validation
    ExtraDefinition(
        name="bypass_address_validation",
        category=ExtraCategory.DELIVERY,
        test_value=True,
        description="Bypass address validation"
    ),

    # Ancillary endorsement (DHL eCommerce)
    ExtraDefinition(
        name="ancillary_endorsement_forwarding",
        category=ExtraCategory.DELIVERY,
        test_value="FORWARDING_SERVICE_REQUESTED",
        description="Ancillary endorsement - forwarding",
        documented_carriers=["dhl_ecommerce"]
    ),
    ExtraDefinition(
        name="ancillary_endorsement_return",
        category=ExtraCategory.DELIVERY,
        test_value="RETURN_SERVICE_REQUESTED",
        description="Ancillary endorsement - return",
        documented_carriers=["dhl_ecommerce"]
    ),

    # DHL Germany specific
    ExtraDefinition(
        name="preferred_delivery_timeframe",
        category=ExtraCategory.DELIVERY,
        test_value="10001200",
        description="Preferred delivery timeframe",
        documented_carriers=["dhl_germany"],
        requires_specific_carrier="dhl_germany"
    ),

    # LaserShip specific
    ExtraDefinition(
        name="lasership_declared_value",
        category=ExtraCategory.CARRIER_SPECIFIC,
        test_value="100.00",
        description="LaserShip declared value",
        documented_carriers=["lasership"],
        requires_specific_carrier="lasership"
    ),
    ExtraDefinition(
        name="lasership_attrs_alcohol",
        category=ExtraCategory.CARRIER_SPECIFIC,
        test_value=["Alcohol"],
        description="LaserShip alcohol attribute",
        documented_carriers=["lasership"],
        requires_specific_carrier="lasership"
    ),
    ExtraDefinition(
        name="lasership_attrs_perishable",
        category=ExtraCategory.CARRIER_SPECIFIC,
        test_value=["Perishable"],
        description="LaserShip perishable attribute",
        documented_carriers=["lasership"],
        requires_specific_carrier="lasership"
    ),
]


# =============================================================================
# Result Types
# =============================================================================

class TestResult(Enum):
    SUPPORTED = "supported"           # Extra was accepted
    NOT_SUPPORTED = "not_supported"   # Explicitly rejected for this carrier/service
    INVALID_VALUE = "invalid_value"   # Extra exists but value was wrong
    ERROR = "error"                   # API error (rate limit, auth, etc.)
    SKIPPED = "skipped"               # Test was skipped (carrier mismatch, etc.)


@dataclass
class ExtraTestResult:
    extra_name: str
    carrier: str
    service_level: str
    result: TestResult
    error_message: Optional[str] = None
    response_data: Optional[dict] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass 
class CarrierCapabilityReport:
    carrier: str
    service_level: str
    supported_extras: list[str]
    unsupported_extras: list[str]
    invalid_value_extras: list[str]
    error_extras: list[str]
    test_timestamp: str


# =============================================================================
# Shippo API Client
# =============================================================================

class ShippoClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"ShippoToken {api_key}",
            "Content-Type": "application/json"
        })
        self.rate_limit_remaining = 100
        self.rate_limit_reset = None

    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make an API request with rate limit handling"""
        url = f"{SHIPPO_API_BASE}{endpoint}"
        
        # Basic rate limit protection
        if self.rate_limit_remaining < 5:
            wait_time = 2
            print(f"  [Rate limit] Waiting {wait_time}s...")
            time.sleep(wait_time)

        response = self.session.request(method, url, json=data)
        
        # Update rate limit tracking
        self.rate_limit_remaining = int(response.headers.get("X-RateLimit-Remaining", 100))
        
        return {
            "status_code": response.status_code,
            "data": response.json() if response.content else {},
            "headers": dict(response.headers)
        }

    def list_carrier_accounts(self, service_levels: bool = True) -> list[dict]:
        """Get all carrier accounts with optional service levels"""
        accounts = []
        page = 1
        while True:
            response = self._request(
                "GET", 
                f"/carrier_accounts?page={page}&results=100&service_levels={str(service_levels).lower()}"
            )
            if response["status_code"] != 200:
                raise Exception(f"Failed to list carrier accounts: {response['data']}")
            
            results = response["data"].get("results", [])
            accounts.extend(results)
            
            if not response["data"].get("next"):
                break
            page += 1
            
        return accounts

    def create_shipment(
        self,
        address_from: dict,
        address_to: dict,
        parcel: dict,
        extra: dict = None,
        carrier_accounts: list[str] = None,
        async_mode: bool = False
    ) -> dict:
        """Create a shipment to test extras"""
        payload = {
            "address_from": address_from,
            "address_to": address_to,
            "parcels": [parcel],
            "async": async_mode
        }
        
        if extra:
            payload["extra"] = extra
            
        if carrier_accounts:
            payload["carrier_accounts"] = carrier_accounts

        return self._request("POST", "/shipments", payload)

    def create_transaction(
        self,
        rate_id: str = None,
        shipment: dict = None,
        carrier_account: str = None,
        servicelevel_token: str = None,
        async_mode: bool = True
    ) -> dict:
        """Create a transaction (doesn't actually purchase in test mode)"""
        if rate_id:
            payload = {"rate": rate_id, "async": async_mode}
        else:
            payload = {
                "shipment": shipment,
                "carrier_account": carrier_account,
                "servicelevel_token": servicelevel_token,
                "async": async_mode
            }
        
        return self._request("POST", "/transactions", payload)


# =============================================================================
# Test Runner
# =============================================================================

class ShippoExtrasTestRunner:
    def __init__(self, api_key: str):
        self.client = ShippoClient(api_key)
        self.results: list[ExtraTestResult] = []
        self.carriers: dict[str, dict] = {}  # carrier_token -> account info

    def discover_carriers(self) -> dict[str, dict]:
        """Discover all connected carriers and their service levels"""
        print("Discovering carrier accounts...")
        accounts = self.client.list_carrier_accounts(service_levels=True)
        
        carriers = {}
        for account in accounts:
            carrier = account.get("carrier", "unknown")
            if carrier not in carriers:
                carriers[carrier] = {
                    "account_id": account.get("object_id"),
                    "carrier": carrier,
                    "active": account.get("active", False),
                    "service_levels": []
                }
            
            # Collect service levels
            service_levels = account.get("service_levels", [])
            for sl in service_levels:
                sl_token = sl.get("token")
                if sl_token and sl_token not in [s["token"] for s in carriers[carrier]["service_levels"]]:
                    carriers[carrier]["service_levels"].append({
                        "token": sl_token,
                        "name": sl.get("name", sl_token),
                        "supports_return_labels": sl.get("supports_return_labels", False)
                    })
        
        self.carriers = carriers
        print(f"Found {len(carriers)} carriers:")
        for carrier, info in carriers.items():
            print(f"  - {carrier}: {len(info['service_levels'])} service levels")
        
        return carriers

    def _build_extra_payload(self, extra_def: ExtraDefinition) -> dict:
        """Build the extra payload for a test"""
        # Map extra names to their API field names
        name = extra_def.name
        value = extra_def.test_value
        
        # Handle signature confirmation variants
        if name.startswith("signature_confirmation"):
            return {"signature_confirmation": value}
        
        # Handle insurance variants
        if name.startswith("insurance"):
            return {"insurance": value}
        
        # Handle COD variants
        if name.startswith("cod"):
            return {"COD": value}
        
        # Handle billing variants
        if name.startswith("billing"):
            return {"billing": value}
        
        # Handle alcohol variants
        if name.startswith("alcohol"):
            return {"alcohol": value}
        
        # Handle dangerous goods variants
        if name.startswith("dangerous_goods_code"):
            return {"dangerous_goods_code": value}
        if name.startswith("dangerous_goods"):
            return {"dangerous_goods": value}
        
        # Handle return service variants
        if name.startswith("return_service"):
            return {"return_service_type": value}
        
        # Handle ancillary endorsement variants
        if name.startswith("ancillary_endorsement"):
            return {"ancillary_endorsement": value}
        
        # Handle lasership attrs variants
        if name.startswith("lasership_attrs"):
            return {"lasership_attrs": value}
        
        # Direct mapping for simple extras
        simple_extras = [
            "saturday_delivery", "authority_to_leave", "delivery_instructions",
            "carbon_neutral", "premium", "reference_1", "reference_2",
            "customer_reference", "po_number", "invoice_number", "dept_number",
            "rma_number", "is_return", "qr_code_requested", "bypass_address_validation",
            "preferred_delivery_timeframe", "lasership_declared_value", "dry_ice"
        ]
        
        if name in simple_extras:
            return {name: value}
        
        # Default - use name as key
        return {name: value}

    def _analyze_response(
        self, 
        response: dict, 
        extra_def: ExtraDefinition,
        carrier: str,
        service_level: str
    ) -> ExtraTestResult:
        """Analyze API response to determine if extra is supported"""
        status_code = response["status_code"]
        data = response["data"]
        
        # Success case - shipment created
        if status_code in [200, 201]:
            # Check if there are any rates returned
            rates = data.get("rates", [])
            messages = data.get("messages", [])
            
            # Look for extra-specific warnings/errors in messages
            extra_rejected = False
            rejection_reason = None
            
            for msg in messages:
                msg_text = msg.get("text", "").lower()
                # Check if the message mentions our extra being rejected
                if any(keyword in msg_text for keyword in [
                    "not supported", "not available", "invalid", 
                    extra_def.name.replace("_", " ").lower()
                ]):
                    extra_rejected = True
                    rejection_reason = msg.get("text")
                    break
            
            if extra_rejected:
                return ExtraTestResult(
                    extra_name=extra_def.name,
                    carrier=carrier,
                    service_level=service_level,
                    result=TestResult.NOT_SUPPORTED,
                    error_message=rejection_reason,
                    response_data={"messages": messages}
                )
            
            # Check if we got rates for the expected carrier/service level
            matching_rates = [
                r for r in rates 
                if r.get("servicelevel", {}).get("token") == service_level
            ]
            
            if matching_rates:
                return ExtraTestResult(
                    extra_name=extra_def.name,
                    carrier=carrier,
                    service_level=service_level,
                    result=TestResult.SUPPORTED,
                    response_data={"rate_count": len(matching_rates)}
                )
            elif rates:
                # Got rates but not for expected service level
                return ExtraTestResult(
                    extra_name=extra_def.name,
                    carrier=carrier,
                    service_level=service_level,
                    result=TestResult.SUPPORTED,
                    response_data={"rate_count": len(rates), "note": "Different service levels returned"}
                )
            else:
                # No rates returned - could be extra not supported or other issue
                return ExtraTestResult(
                    extra_name=extra_def.name,
                    carrier=carrier,
                    service_level=service_level,
                    result=TestResult.NOT_SUPPORTED,
                    error_message="No rates returned",
                    response_data={"messages": messages}
                )
        
        # Error case
        elif status_code == 400:
            error_messages = data.get("messages", data.get("detail", str(data)))
            error_text = str(error_messages).lower()
            
            # Check if error is specifically about the extra
            if any(keyword in error_text for keyword in [
                "not supported", "not available", "not valid", "invalid extra",
                extra_def.name.replace("_", " ").lower()
            ]):
                return ExtraTestResult(
                    extra_name=extra_def.name,
                    carrier=carrier,
                    service_level=service_level,
                    result=TestResult.NOT_SUPPORTED,
                    error_message=str(error_messages)
                )
            
            # Check if it's a value validation error
            if any(keyword in error_text for keyword in [
                "invalid value", "must be", "required", "format"
            ]):
                return ExtraTestResult(
                    extra_name=extra_def.name,
                    carrier=carrier,
                    service_level=service_level,
                    result=TestResult.INVALID_VALUE,
                    error_message=str(error_messages)
                )
            
            # Generic bad request - likely not supported
            return ExtraTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=TestResult.NOT_SUPPORTED,
                error_message=str(error_messages)
            )
        
        elif status_code == 401:
            return ExtraTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=TestResult.ERROR,
                error_message="Authentication failed"
            )
        
        elif status_code == 429:
            return ExtraTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=TestResult.ERROR,
                error_message="Rate limited"
            )
        
        else:
            return ExtraTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=TestResult.ERROR,
                error_message=f"Unexpected status {status_code}: {data}"
            )

    def test_extra(
        self,
        extra_def: ExtraDefinition,
        carrier: str,
        service_level: str,
        carrier_account_id: str
    ) -> ExtraTestResult:
        """Test a single extra against a carrier/service level"""
        
        # Skip if extra requires specific carrier
        if extra_def.requires_specific_carrier and extra_def.requires_specific_carrier != carrier:
            return ExtraTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=TestResult.SKIPPED,
                error_message=f"Extra requires carrier: {extra_def.requires_specific_carrier}"
            )
        
        # Build the extra payload
        extra_payload = self._build_extra_payload(extra_def)
        
        # Choose addresses based on whether international is required
        address_to = TEST_ADDRESS_INTERNATIONAL if extra_def.requires_international else TEST_ADDRESS_TO
        
        # Create shipment with the extra
        response = self.client.create_shipment(
            address_from=TEST_ADDRESS_FROM,
            address_to=address_to,
            parcel=TEST_PARCEL,
            extra=extra_payload,
            carrier_accounts=[carrier_account_id]
        )
        
        # Analyze the response
        return self._analyze_response(response, extra_def, carrier, service_level)

    def run_all_tests(
        self,
        carriers_filter: list[str] = None,
        service_levels_filter: list[str] = None,
        extras_filter: list[str] = None,
        max_tests: int = None
    ) -> list[ExtraTestResult]:
        """Run tests for all combinations"""
        
        if not self.carriers:
            self.discover_carriers()
        
        test_count = 0
        total_tests = 0
        
        # Calculate total tests
        for carrier, info in self.carriers.items():
            if carriers_filter and carrier not in carriers_filter:
                continue
            for sl in info["service_levels"]:
                if service_levels_filter and sl["token"] not in service_levels_filter:
                    continue
                for extra_def in EXTRAS_TO_TEST:
                    if extras_filter and extra_def.name not in extras_filter:
                        continue
                    total_tests += 1
        
        print(f"\nRunning {total_tests} tests...")
        
        for carrier, info in self.carriers.items():
            if carriers_filter and carrier not in carriers_filter:
                continue
            
            if not info["active"]:
                print(f"\nSkipping inactive carrier: {carrier}")
                continue
            
            print(f"\n{'='*60}")
            print(f"Testing carrier: {carrier}")
            print(f"{'='*60}")
            
            for sl in info["service_levels"]:
                if service_levels_filter and sl["token"] not in service_levels_filter:
                    continue
                
                print(f"\n  Service Level: {sl['name']} ({sl['token']})")
                print(f"  {'-'*50}")
                
                for extra_def in EXTRAS_TO_TEST:
                    if extras_filter and extra_def.name not in extras_filter:
                        continue
                    
                    if max_tests and test_count >= max_tests:
                        print(f"\n  Reached max tests limit ({max_tests})")
                        return self.results
                    
                    print(f"    Testing: {extra_def.name}...", end=" ", flush=True)
                    
                    try:
                        result = self.test_extra(
                            extra_def=extra_def,
                            carrier=carrier,
                            service_level=sl["token"],
                            carrier_account_id=info["account_id"]
                        )
                        self.results.append(result)
                        
                        # Print result
                        if result.result == TestResult.SUPPORTED:
                            print("✓ SUPPORTED")
                        elif result.result == TestResult.NOT_SUPPORTED:
                            print(f"✗ NOT SUPPORTED ({result.error_message[:50] if result.error_message else 'N/A'}...)")
                        elif result.result == TestResult.INVALID_VALUE:
                            print(f"⚠ INVALID VALUE ({result.error_message[:50] if result.error_message else 'N/A'}...)")
                        elif result.result == TestResult.SKIPPED:
                            print(f"⊘ SKIPPED ({result.error_message})")
                        else:
                            print(f"⚡ ERROR ({result.error_message[:50] if result.error_message else 'N/A'}...)")
                        
                        test_count += 1
                        
                        # Small delay to avoid rate limiting
                        time.sleep(0.5)
                        
                    except Exception as e:
                        print(f"⚡ EXCEPTION: {str(e)[:50]}")
                        self.results.append(ExtraTestResult(
                            extra_name=extra_def.name,
                            carrier=carrier,
                            service_level=sl["token"],
                            result=TestResult.ERROR,
                            error_message=str(e)
                        ))
        
        return self.results

    def generate_report(self) -> dict:
        """Generate a summary report of all test results"""
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "total_tests": len(self.results),
            "summary": {
                "supported": 0,
                "not_supported": 0,
                "invalid_value": 0,
                "error": 0,
                "skipped": 0
            },
            "by_carrier": {},
            "by_extra": {},
            "capability_matrix": []
        }
        
        # Count results
        for result in self.results:
            report["summary"][result.result.value] += 1
            
            # By carrier
            carrier_key = f"{result.carrier}:{result.service_level}"
            if carrier_key not in report["by_carrier"]:
                report["by_carrier"][carrier_key] = {
                    "carrier": result.carrier,
                    "service_level": result.service_level,
                    "supported": [],
                    "not_supported": [],
                    "invalid_value": [],
                    "error": [],
                    "skipped": []
                }
            report["by_carrier"][carrier_key][result.result.value].append(result.extra_name)
            
            # By extra
            if result.extra_name not in report["by_extra"]:
                report["by_extra"][result.extra_name] = {
                    "supported_by": [],
                    "not_supported_by": []
                }
            if result.result == TestResult.SUPPORTED:
                report["by_extra"][result.extra_name]["supported_by"].append(carrier_key)
            elif result.result == TestResult.NOT_SUPPORTED:
                report["by_extra"][result.extra_name]["not_supported_by"].append(carrier_key)
        
        # Build capability matrix
        for carrier_key, data in report["by_carrier"].items():
            report["capability_matrix"].append(
                CarrierCapabilityReport(
                    carrier=data["carrier"],
                    service_level=data["service_level"],
                    supported_extras=data["supported"],
                    unsupported_extras=data["not_supported"],
                    invalid_value_extras=data["invalid_value"],
                    error_extras=data["error"],
                    test_timestamp=report["generated_at"]
                )
            )
        
        return report


# =============================================================================
# Output Formatters
# =============================================================================

def save_results_json(results: list[ExtraTestResult], filename: str):
    """Save results to JSON file"""
    data = [asdict(r) for r in results]
    with open(filename, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Results saved to {filename}")


def save_report_json(report: dict, filename: str):
    """Save report to JSON file"""
    # Convert dataclasses in capability_matrix
    report_copy = report.copy()
    report_copy["capability_matrix"] = [asdict(c) for c in report["capability_matrix"]]
    
    with open(filename, "w") as f:
        json.dump(report_copy, f, indent=2, default=str)
    print(f"Report saved to {filename}")


def generate_markdown_report(report: dict) -> str:
    """Generate a markdown report"""
    md = []
    md.append("# Shippo Extras Capability Report")
    md.append(f"\nGenerated: {report['generated_at']}")
    md.append(f"\nTotal Tests: {report['total_tests']}")
    
    md.append("\n## Summary")
    md.append(f"- Supported: {report['summary']['supported']}")
    md.append(f"- Not Supported: {report['summary']['not_supported']}")
    md.append(f"- Invalid Value: {report['summary']['invalid_value']}")
    md.append(f"- Errors: {report['summary']['error']}")
    md.append(f"- Skipped: {report['summary']['skipped']}")
    
    md.append("\n## Extras Support by Carrier/Service Level")
    for cap in report["capability_matrix"]:
        if isinstance(cap, dict):
            carrier = cap["carrier"]
            service_level = cap["service_level"]
            supported = cap["supported_extras"]
            unsupported = cap["unsupported_extras"]
        else:
            carrier = cap.carrier
            service_level = cap.service_level
            supported = cap.supported_extras
            unsupported = cap.unsupported_extras
        
        md.append(f"\n### {carrier} - {service_level}")
        
        if supported:
            md.append("\n**Supported Extras:**")
            for extra in sorted(supported):
                md.append(f"- ✓ {extra}")
        
        if unsupported:
            md.append("\n**Not Supported:**")
            for extra in sorted(unsupported):
                md.append(f"- ✗ {extra}")
    
    md.append("\n## Extras Availability Across Carriers")
    for extra_name, data in sorted(report["by_extra"].items()):
        md.append(f"\n### {extra_name}")
        if data["supported_by"]:
            md.append(f"- Supported by: {', '.join(data['supported_by'])}")
        if data["not_supported_by"]:
            md.append(f"- Not supported by: {', '.join(data['not_supported_by'])}")
    
    return "\n".join(md)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Test Shippo extras support by carrier and service level"
    )
    parser.add_argument(
        "--carrier", "-c",
        help="Filter to specific carrier(s)",
        action="append",
        dest="carriers"
    )
    parser.add_argument(
        "--service-level", "-s",
        help="Filter to specific service level(s)",
        action="append",
        dest="service_levels"
    )
    parser.add_argument(
        "--extra", "-e",
        help="Filter to specific extra(s)",
        action="append",
        dest="extras"
    )
    parser.add_argument(
        "--max-tests", "-m",
        type=int,
        help="Maximum number of tests to run"
    )
    parser.add_argument(
        "--output", "-o",
        default="shippo_extras_results",
        help="Output filename prefix (default: shippo_extras_results)"
    )
    parser.add_argument(
        "--list-extras",
        action="store_true",
        help="List all available extras and exit"
    )
    parser.add_argument(
        "--list-carriers",
        action="store_true",
        help="List all available carriers and exit"
    )
    
    args = parser.parse_args()
    
    # List extras if requested
    if args.list_extras:
        print("\nAvailable Extras to Test:")
        print("=" * 60)
        for extra in EXTRAS_TO_TEST:
            carriers = ", ".join(extra.documented_carriers) if extra.documented_carriers else "Unknown"
            print(f"  {extra.name}")
            print(f"    Category: {extra.category.value}")
            print(f"    Description: {extra.description}")
            print(f"    Documented carriers: {carriers}")
            print()
        return
    
    # Get API key
    api_key = os.environ.get("SHIPPO_API_KEY")
    if not api_key:
        print("Error: SHIPPO_API_KEY environment variable not set")
        print("Usage: export SHIPPO_API_KEY='your_api_key_here'")
        return
    
    # Initialize runner
    runner = ShippoExtrasTestRunner(api_key)
    
    # List carriers if requested
    if args.list_carriers:
        runner.discover_carriers()
        print("\nAvailable Carriers and Service Levels:")
        print("=" * 60)
        for carrier, info in runner.carriers.items():
            status = "Active" if info["active"] else "Inactive"
            print(f"\n{carrier} ({status})")
            print(f"  Account ID: {info['account_id']}")
            print(f"  Service Levels:")
            for sl in info["service_levels"]:
                print(f"    - {sl['token']}: {sl['name']}")
        return
    
    # Run tests
    print("\n" + "=" * 60)
    print("Shippo Extras Discovery Test Suite")
    print("=" * 60)
    
    results = runner.run_all_tests(
        carriers_filter=args.carriers,
        service_levels_filter=args.service_levels,
        extras_filter=args.extras,
        max_tests=args.max_tests
    )
    
    # Generate report
    report = runner.generate_report()
    
    # Save outputs
    save_results_json(results, f"{args.output}_raw.json")
    save_report_json(report, f"{args.output}_report.json")
    
    # Generate and save markdown report
    md_report = generate_markdown_report(report)
    with open(f"{args.output}_report.md", "w") as f:
        f.write(md_report)
    print(f"Markdown report saved to {args.output}_report.md")
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total tests: {report['total_tests']}")
    print(f"  Supported: {report['summary']['supported']}")
    print(f"  Not Supported: {report['summary']['not_supported']}")
    print(f"  Invalid Value: {report['summary']['invalid_value']}")
    print(f"  Errors: {report['summary']['error']}")
    print(f"  Skipped: {report['summary']['skipped']}")


if __name__ == "__main__":
    main()
