"""
Service Level Specific Extras Testing

Some extras are only available for specific service levels within a carrier.
This module provides tools to discover and document these relationships.

Examples of service-level-specific extras:
- Saturday delivery: Usually only for express services
- Signature confirmation types: May vary by service level
- Insurance limits: Often differ by service class
- Hazmat: Only certain service levels are certified
"""

import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

from test_shippo_extras import (
    ShippoClient,
    ExtraDefinition,
    ExtraCategory,
    TEST_ADDRESS_FROM,
    TEST_ADDRESS_TO,
    TEST_PARCEL
)


# =============================================================================
# Service Level Categories
# =============================================================================

class ServiceCategory(Enum):
    """Categorization of service levels for testing purposes"""
    EXPRESS = "express"           # Next day, overnight
    EXPEDITED = "expedited"       # 2-3 day
    GROUND = "ground"             # Standard ground
    ECONOMY = "economy"           # Budget/slow
    FREIGHT = "freight"           # LTL/freight
    INTERNATIONAL = "international"
    RETURNS = "returns"
    SPECIALTY = "specialty"       # Hazmat, alcohol, etc.


# Known service level categorizations (expand as needed)
SERVICE_LEVEL_CATEGORIES = {
    # USPS
    "usps_priority": ServiceCategory.EXPEDITED,
    "usps_priority_express": ServiceCategory.EXPRESS,
    "usps_first": ServiceCategory.GROUND,
    "usps_parcel_select": ServiceCategory.ECONOMY,
    "usps_media_mail": ServiceCategory.ECONOMY,
    "usps_priority_mail_international": ServiceCategory.INTERNATIONAL,
    "usps_first_class_package_international_service": ServiceCategory.INTERNATIONAL,
    
    # FedEx
    "fedex_ground": ServiceCategory.GROUND,
    "fedex_home_delivery": ServiceCategory.GROUND,
    "fedex_2_day": ServiceCategory.EXPEDITED,
    "fedex_2_day_am": ServiceCategory.EXPEDITED,
    "fedex_express_saver": ServiceCategory.EXPEDITED,
    "fedex_standard_overnight": ServiceCategory.EXPRESS,
    "fedex_priority_overnight": ServiceCategory.EXPRESS,
    "fedex_first_overnight": ServiceCategory.EXPRESS,
    "fedex_freight_economy": ServiceCategory.FREIGHT,
    "fedex_freight_priority": ServiceCategory.FREIGHT,
    "fedex_international_economy": ServiceCategory.INTERNATIONAL,
    "fedex_international_priority": ServiceCategory.INTERNATIONAL,
    
    # UPS
    "ups_ground": ServiceCategory.GROUND,
    "ups_3_day_select": ServiceCategory.EXPEDITED,
    "ups_2nd_day_air": ServiceCategory.EXPEDITED,
    "ups_2nd_day_air_am": ServiceCategory.EXPEDITED,
    "ups_next_day_air_saver": ServiceCategory.EXPRESS,
    "ups_next_day_air": ServiceCategory.EXPRESS,
    "ups_next_day_air_early_am": ServiceCategory.EXPRESS,
    "ups_standard": ServiceCategory.INTERNATIONAL,
    "ups_worldwide_expedited": ServiceCategory.INTERNATIONAL,
    "ups_worldwide_express": ServiceCategory.INTERNATIONAL,
    
    # DHL
    "dhl_express_worldwide": ServiceCategory.INTERNATIONAL,
    "dhl_express_1200": ServiceCategory.EXPRESS,
    "dhl_economy_select": ServiceCategory.ECONOMY,
}


# =============================================================================
# Service Level Specific Extra Rules
# =============================================================================

@dataclass
class ServiceLevelExtraRule:
    """Defines expected extra support by service category"""
    extra_name: str
    supported_categories: list[ServiceCategory]
    notes: str = ""


# Expected service level restrictions (based on carrier documentation)
EXPECTED_SERVICE_RULES = [
    ServiceLevelExtraRule(
        extra_name="saturday_delivery",
        supported_categories=[ServiceCategory.EXPRESS, ServiceCategory.EXPEDITED],
        notes="Generally only express/expedited services offer Saturday delivery"
    ),
    ServiceLevelExtraRule(
        extra_name="signature_confirmation_certified",
        supported_categories=[ServiceCategory.GROUND, ServiceCategory.EXPEDITED],
        notes="USPS Certified Mail is typically First Class or Priority"
    ),
    ServiceLevelExtraRule(
        extra_name="cod_any",
        supported_categories=[ServiceCategory.GROUND, ServiceCategory.EXPEDITED, ServiceCategory.EXPRESS],
        notes="COD typically not available for economy services"
    ),
    ServiceLevelExtraRule(
        extra_name="dangerous_goods",
        supported_categories=[ServiceCategory.GROUND, ServiceCategory.EXPEDITED],
        notes="Hazmat often restricted to ground and certain air services"
    ),
    ServiceLevelExtraRule(
        extra_name="alcohol_consumer",
        supported_categories=[ServiceCategory.GROUND, ServiceCategory.EXPEDITED, ServiceCategory.EXPRESS],
        notes="Alcohol shipping requires specific licensing and service levels"
    ),
]


# =============================================================================
# Test Result Types
# =============================================================================

@dataclass
class ServiceLevelTestResult:
    """Result of testing an extra at a specific service level"""
    carrier: str
    service_level: str
    service_category: Optional[ServiceCategory]
    extra_name: str
    
    # Test outcome
    is_supported: bool
    support_type: str  # "accepted", "rate_modified", "rejected", "ignored", "error"
    
    # Details
    error_message: Optional[str] = None
    rate_impact: Optional[float] = None
    
    # Metadata
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ServiceLevelMatrix:
    """Matrix of extra support by service level"""
    carrier: str
    service_level: str
    category: Optional[ServiceCategory]
    
    # Categorized extras
    fully_supported: list[str] = field(default_factory=list)
    rate_impacting: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# =============================================================================
# Detailed Service Level Tester
# =============================================================================

class ServiceLevelExtrasAnalyzer:
    """
    Analyzes extras support at the service level granularity.
    
    Key insights this provides:
    1. Which extras are service-level specific
    2. Which extras affect rates (strong indicator of support)
    3. Which extras are silently ignored vs. explicitly rejected
    """
    
    def __init__(self, api_key: str):
        self.client = ShippoClient(api_key)
        self.results: list[ServiceLevelTestResult] = []
        
    def categorize_service_level(self, token: str) -> Optional[ServiceCategory]:
        """Attempt to categorize a service level"""
        # Direct lookup
        if token in SERVICE_LEVEL_CATEGORIES:
            return SERVICE_LEVEL_CATEGORIES[token]
        
        # Pattern matching
        token_lower = token.lower()
        
        if any(x in token_lower for x in ["overnight", "express", "next_day", "1_day"]):
            return ServiceCategory.EXPRESS
        if any(x in token_lower for x in ["2_day", "2nd_day", "expedited", "priority"]):
            return ServiceCategory.EXPEDITED
        if any(x in token_lower for x in ["ground", "home", "standard"]):
            return ServiceCategory.GROUND
        if any(x in token_lower for x in ["economy", "saver", "parcel_select", "media"]):
            return ServiceCategory.ECONOMY
        if any(x in token_lower for x in ["freight", "ltl"]):
            return ServiceCategory.FREIGHT
        if any(x in token_lower for x in ["international", "worldwide", "global"]):
            return ServiceCategory.INTERNATIONAL
        if any(x in token_lower for x in ["return"]):
            return ServiceCategory.RETURNS
        
        return None
    
    def analyze_carrier_service_levels(
        self,
        carrier: str,
        carrier_account_id: str,
        service_levels: list[dict],
        extras_to_test: list[ExtraDefinition]
    ) -> list[ServiceLevelMatrix]:
        """Analyze extras support across all service levels for a carrier"""
        
        matrices = []
        
        for sl in service_levels:
            sl_token = sl["token"]
            category = self.categorize_service_level(sl_token)
            
            print(f"\n  Analyzing {sl_token} ({category.value if category else 'unknown'})...")
            
            matrix = ServiceLevelMatrix(
                carrier=carrier,
                service_level=sl_token,
                category=category
            )
            
            # Get baseline
            baseline = self._get_baseline_rate(carrier_account_id, sl_token)
            
            if baseline is None:
                print(f"    Baseline failed - skipping service level")
                continue
            
            for extra_def in extras_to_test:
                result = self._test_extra_at_service_level(
                    extra_def=extra_def,
                    carrier=carrier,
                    service_level=sl_token,
                    carrier_account_id=carrier_account_id,
                    baseline_rate=baseline,
                    category=category
                )
                
                self.results.append(result)
                
                # Categorize result
                if result.support_type == "accepted":
                    matrix.fully_supported.append(extra_def.name)
                elif result.support_type == "rate_modified":
                    matrix.rate_impacting.append(extra_def.name)
                elif result.support_type == "rejected":
                    matrix.rejected.append(extra_def.name)
                elif result.support_type == "ignored":
                    matrix.ignored.append(extra_def.name)
                else:
                    matrix.errors.append(extra_def.name)
            
            matrices.append(matrix)
        
        return matrices
    
    def _get_baseline_rate(
        self,
        carrier_account_id: str,
        service_level: str
    ) -> Optional[dict]:
        """Get baseline rate for a service level"""
        response = self.client.create_shipment(
            address_from=TEST_ADDRESS_FROM,
            address_to=TEST_ADDRESS_TO,
            parcel=TEST_PARCEL,
            carrier_accounts=[carrier_account_id]
        )
        
        if response["status_code"] not in [200, 201]:
            return None
        
        rates = response["data"].get("rates", [])
        matching = [r for r in rates if r.get("servicelevel", {}).get("token") == service_level]
        
        if not matching:
            return None
        
        return {
            "amount": float(matching[0].get("amount", 0)),
            "rate_id": matching[0].get("object_id"),
            "service_level": service_level
        }
    
    def _test_extra_at_service_level(
        self,
        extra_def: ExtraDefinition,
        carrier: str,
        service_level: str,
        carrier_account_id: str,
        baseline_rate: dict,
        category: Optional[ServiceCategory]
    ) -> ServiceLevelTestResult:
        """Test a specific extra at a specific service level"""
        
        # Build extra payload
        extra_payload = self._build_extra(extra_def)
        
        # Make request
        response = self.client.create_shipment(
            address_from=TEST_ADDRESS_FROM,
            address_to=TEST_ADDRESS_TO,
            parcel=TEST_PARCEL,
            extra=extra_payload,
            carrier_accounts=[carrier_account_id]
        )
        
        # Analyze
        if response["status_code"] not in [200, 201]:
            return ServiceLevelTestResult(
                carrier=carrier,
                service_level=service_level,
                service_category=category,
                extra_name=extra_def.name,
                is_supported=False,
                support_type="rejected",
                error_message=str(response["data"])
            )
        
        rates = response["data"].get("rates", [])
        matching = [r for r in rates if r.get("servicelevel", {}).get("token") == service_level]
        
        if not matching:
            return ServiceLevelTestResult(
                carrier=carrier,
                service_level=service_level,
                service_category=category,
                extra_name=extra_def.name,
                is_supported=False,
                support_type="rejected",
                error_message="Service level not available with this extra"
            )
        
        new_amount = float(matching[0].get("amount", 0))
        rate_diff = new_amount - baseline_rate["amount"]
        
        if abs(rate_diff) > 0.01:
            return ServiceLevelTestResult(
                carrier=carrier,
                service_level=service_level,
                service_category=category,
                extra_name=extra_def.name,
                is_supported=True,
                support_type="rate_modified",
                rate_impact=rate_diff
            )
        
        # Same rate - check for messages
        messages = response["data"].get("messages", [])
        extra_mentioned = any(
            extra_def.name.replace("_", " ").lower() in str(m).lower()
            for m in messages
        )
        
        if extra_mentioned:
            return ServiceLevelTestResult(
                carrier=carrier,
                service_level=service_level,
                service_category=category,
                extra_name=extra_def.name,
                is_supported=True,
                support_type="accepted"
            )
        
        return ServiceLevelTestResult(
            carrier=carrier,
            service_level=service_level,
            service_category=category,
            extra_name=extra_def.name,
            is_supported=False,
            support_type="ignored"
        )
    
    def _build_extra(self, extra_def: ExtraDefinition) -> dict:
        """Build extra payload"""
        name = extra_def.name
        value = extra_def.test_value
        
        mappings = {
            "signature_confirmation": "signature_confirmation",
            "insurance": "insurance",
            "cod": "COD",
            "billing": "billing",
            "alcohol": "alcohol",
            "dangerous_goods_code": "dangerous_goods_code",
            "dangerous_goods": "dangerous_goods",
            "return_service": "return_service_type",
            "ancillary_endorsement": "ancillary_endorsement",
            "lasership_attrs": "lasership_attrs",
        }
        
        for prefix, field_name in mappings.items():
            if name.startswith(prefix):
                return {field_name: value}
        
        return {name: value}


# =============================================================================
# Report Generation
# =============================================================================

def generate_service_level_report(matrices: list[ServiceLevelMatrix]) -> str:
    """Generate detailed service level report"""
    md = []
    md.append("# Service Level Specific Extras Report")
    md.append(f"\nGenerated: {datetime.utcnow().isoformat()}")
    
    # Group by carrier
    by_carrier = {}
    for matrix in matrices:
        if matrix.carrier not in by_carrier:
            by_carrier[matrix.carrier] = []
        by_carrier[matrix.carrier].append(matrix)
    
    for carrier, carrier_matrices in sorted(by_carrier.items()):
        md.append(f"\n## {carrier.upper()}")
        
        # Summary table
        md.append("\n### Support Summary")
        md.append("\n| Service Level | Category | Supported | Rate Impact | Rejected | Ignored |")
        md.append("|---------------|----------|-----------|-------------|----------|---------|")
        
        for m in carrier_matrices:
            cat = m.category.value if m.category else "?"
            md.append(f"| {m.service_level} | {cat} | {len(m.fully_supported)} | {len(m.rate_impacting)} | {len(m.rejected)} | {len(m.ignored)} |")
        
        # Detail by service level
        for m in carrier_matrices:
            cat = m.category.value if m.category else "unknown"
            md.append(f"\n### {m.service_level} ({cat})")
            
            if m.fully_supported:
                md.append(f"\n**Fully Supported:** {', '.join(m.fully_supported)}")
            if m.rate_impacting:
                md.append(f"\n**Rate Impacting:** {', '.join(m.rate_impacting)}")
            if m.rejected:
                md.append(f"\n**Rejected:** {', '.join(m.rejected)}")
            if m.ignored:
                md.append(f"\n**Ignored/Unknown:** {', '.join(m.ignored)}")
    
    # Cross-service-level analysis
    md.append("\n## Cross-Service-Level Analysis")
    md.append("\nExtras that vary by service level within a carrier:")
    
    for carrier, carrier_matrices in sorted(by_carrier.items()):
        md.append(f"\n### {carrier}")
        
        # Find extras with inconsistent support
        all_extras = set()
        for m in carrier_matrices:
            all_extras.update(m.fully_supported)
            all_extras.update(m.rate_impacting)
            all_extras.update(m.rejected)
            all_extras.update(m.ignored)
        
        for extra in sorted(all_extras):
            support_map = []
            for m in carrier_matrices:
                if extra in m.fully_supported or extra in m.rate_impacting:
                    support_map.append(f"{m.service_level}:✓")
                elif extra in m.rejected:
                    support_map.append(f"{m.service_level}:✗")
                else:
                    support_map.append(f"{m.service_level}:?")
            
            # Check if support varies
            statuses = [s.split(":")[1] for s in support_map]
            if len(set(statuses)) > 1:  # Varies
                md.append(f"\n- **{extra}**: {', '.join(support_map)}")
    
    return "\n".join(md)


def save_service_level_results(
    matrices: list[ServiceLevelMatrix],
    results: list[ServiceLevelTestResult],
    output_prefix: str
):
    """Save all results"""
    # Save raw results
    with open(f"{output_prefix}_results.json", "w") as f:
        data = []
        for r in results:
            d = asdict(r)
            d["service_category"] = r.service_category.value if r.service_category else None
            data.append(d)
        json.dump(data, f, indent=2)
    
    # Save matrices
    with open(f"{output_prefix}_matrices.json", "w") as f:
        data = []
        for m in matrices:
            d = asdict(m)
            d["category"] = m.category.value if m.category else None
            data.append(d)
        json.dump(data, f, indent=2)
    
    # Save markdown report
    md = generate_service_level_report(matrices)
    with open(f"{output_prefix}_report.md", "w") as f:
        f.write(md)
    
    print(f"Results saved to {output_prefix}_*")


if __name__ == "__main__":
    import os
    import argparse
    from test_shippo_extras import ShippoExtrasTestRunner, EXTRAS_TO_TEST
    
    parser = argparse.ArgumentParser(description="Analyze service level specific extras")
    parser.add_argument("--carrier", "-c", action="append", dest="carriers")
    parser.add_argument("--output", "-o", default="shippo_service_level")
    
    args = parser.parse_args()
    
    api_key = os.environ.get("SHIPPO_API_KEY")
    if not api_key:
        print("Error: SHIPPO_API_KEY not set")
        exit(1)
    
    # Discover carriers
    discovery = ShippoExtrasTestRunner(api_key)
    carriers = discovery.discover_carriers()
    
    # Analyze
    analyzer = ServiceLevelExtrasAnalyzer(api_key)
    all_matrices = []
    
    for carrier, info in carriers.items():
        if args.carriers and carrier not in args.carriers:
            continue
        
        if not info.get("active"):
            continue
        
        print(f"\n{'='*60}")
        print(f"Analyzing {carrier}")
        print(f"{'='*60}")
        
        matrices = analyzer.analyze_carrier_service_levels(
            carrier=carrier,
            carrier_account_id=info["account_id"],
            service_levels=info["service_levels"],
            extras_to_test=EXTRAS_TO_TEST
        )
        all_matrices.extend(matrices)
    
    # Save
    save_service_level_results(all_matrices, analyzer.results, args.output)
