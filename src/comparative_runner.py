"""
Comparative Extras Runner (Async Version)

This module provides a sophisticated validation approach:
1. First creates a baseline shipment WITHOUT extras
2. Then creates shipments WITH each extra
3. Compares responses to determine actual extra support

This handles cases where:
- A carrier might reject a shipment for reasons unrelated to extras
- Service levels might not be available for addresses
- Extras might be silently ignored vs. explicitly rejected

Usage:
    export SHIPPO_API_KEY="your_api_key_here"
    python comparative_runner.py --carrier usps --concurrency 10
"""

import os
import json
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
from enum import Enum

from shippo_extras import (
    ShippoClient,
    EXTRAS_TO_TEST,
    ExtraDefinition,
    TEST_ADDRESS_FROM,
    TEST_ADDRESS_TO,
    TEST_ADDRESS_INTERNATIONAL,
    TEST_PARCEL,
    DEFAULT_CONCURRENCY
)


class ComparativeResult(Enum):
    """Results from comparative testing"""
    EXTRA_ACCEPTED = "extra_accepted"              # Extra was accepted, rates returned
    EXTRA_REJECTED = "extra_rejected"              # Extra caused rejection (vs baseline)
    EXTRA_IGNORED = "extra_ignored"                # Extra had no effect (same as baseline)
    EXTRA_MODIFIED_RATES = "extra_modified_rates"  # Extra changed available rates/prices
    BASELINE_FAILED = "baseline_failed"            # Baseline shipment failed
    ERROR = "error"


@dataclass
class ComparativeTestResult:
    """Result of a comparative test"""
    extra_name: str
    carrier: str
    service_level: str
    result: ComparativeResult

    # Baseline info
    baseline_rate_count: int = 0
    baseline_rate_ids: list[str] = None
    baseline_messages: list[str] = None

    # With-extra info
    extra_rate_count: int = 0
    extra_rate_ids: list[str] = None
    extra_messages: list[str] = None

    # Rate comparison
    rate_price_change: Optional[float] = None
    rate_availability_change: Optional[str] = None

    error_message: Optional[str] = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
        if self.baseline_rate_ids is None:
            self.baseline_rate_ids = []
        if self.extra_rate_ids is None:
            self.extra_rate_ids = []
        if self.baseline_messages is None:
            self.baseline_messages = []
        if self.extra_messages is None:
            self.extra_messages = []


class ComparativeTestRunner:
    """Runs comparative tests to determine extra support (async version)"""

    def __init__(self, api_key: str, concurrency: int = DEFAULT_CONCURRENCY):
        self.api_key = api_key
        self.concurrency = concurrency
        self.baseline_cache: dict[str, dict] = {}  # carrier:service_level -> baseline result
        self.results: list[ComparativeTestResult] = []
        self._baseline_lock = asyncio.Lock()

    def _extract_rate_info(self, response: dict) -> dict:
        """Extract rate information from response"""
        data = response.get("data", {})
        rates = data.get("rates", [])
        messages = data.get("messages", [])

        return {
            "success": response.get("status_code") in [200, 201],
            "status_code": response.get("status_code"),
            "rate_count": len(rates),
            "rates": [
                {
                    "id": r.get("object_id"),
                    "carrier": r.get("provider"),
                    "service_level": r.get("servicelevel", {}).get("token"),
                    "amount": float(r.get("amount", 0)),
                    "currency": r.get("currency"),
                    "estimated_days": r.get("estimated_days")
                }
                for r in rates
            ],
            "messages": [m.get("text", str(m)) for m in messages],
            "raw_data": data
        }

    async def get_baseline(
        self,
        client: ShippoClient,
        carrier: str,
        service_level: str,
        carrier_account_id: str,
        use_international: bool = False
    ) -> dict:
        """Get or create baseline shipment for carrier/service level (with cache locking)"""
        cache_key = f"{carrier}:{service_level}:{'intl' if use_international else 'domestic'}"

        # Check cache first
        async with self._baseline_lock:
            if cache_key in self.baseline_cache:
                return self.baseline_cache[cache_key]

        address_to = TEST_ADDRESS_INTERNATIONAL if use_international else TEST_ADDRESS_TO

        response = await client.create_shipment(
            address_from=TEST_ADDRESS_FROM,
            address_to=address_to,
            parcel=TEST_PARCEL,
            carrier_accounts=[carrier_account_id]
        )

        baseline = self._extract_rate_info(response)

        # Store in cache with lock
        async with self._baseline_lock:
            self.baseline_cache[cache_key] = baseline

        return baseline

    def _build_extra_payload(self, extra_def: ExtraDefinition) -> dict:
        """Build the extra payload for testing"""
        name = extra_def.name
        value = extra_def.test_value

        # Handle variants
        field_mappings = {
            "signature_confirmation": ["signature_confirmation"],
            "insurance": ["insurance"],
            "cod": ["COD"],
            "billing": ["billing"],
            "alcohol": ["alcohol"],
            "dangerous_goods_code": ["dangerous_goods_code"],
            "dangerous_goods": ["dangerous_goods"],
            "return_service": ["return_service_type"],
            "ancillary_endorsement": ["ancillary_endorsement"],
            "lasership_attrs": ["lasership_attrs"],
        }

        for prefix, field_names in field_mappings.items():
            if name.startswith(prefix):
                return {field_names[0]: value}

        return {name: value}

    async def test_extra_comparative(
        self,
        client: ShippoClient,
        extra_def: ExtraDefinition,
        carrier: str,
        service_level: str,
        carrier_account_id: str
    ) -> ComparativeTestResult:
        """Test an extra using comparative approach"""

        # Skip if extra requires different carrier
        if extra_def.requires_specific_carrier and extra_def.requires_specific_carrier != carrier:
            return ComparativeTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=ComparativeResult.ERROR,
                error_message=f"Requires carrier: {extra_def.requires_specific_carrier}"
            )

        use_international = extra_def.requires_international

        # Get baseline (cached)
        try:
            baseline = await self.get_baseline(
                client, carrier, service_level, carrier_account_id, use_international
            )
        except Exception as e:
            return ComparativeTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=ComparativeResult.BASELINE_FAILED,
                error_message=str(e)
            )

        if not baseline["success"]:
            return ComparativeTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=ComparativeResult.BASELINE_FAILED,
                baseline_rate_count=baseline["rate_count"],
                baseline_messages=baseline["messages"],
                error_message=f"Baseline failed with status {baseline['status_code']}"
            )

        # Test with extra
        extra_payload = self._build_extra_payload(extra_def)
        address_to = TEST_ADDRESS_INTERNATIONAL if use_international else TEST_ADDRESS_TO

        try:
            response = await client.create_shipment(
                address_from=TEST_ADDRESS_FROM,
                address_to=address_to,
                parcel=TEST_PARCEL,
                extra=extra_payload,
                carrier_accounts=[carrier_account_id]
            )
            extra_info = self._extract_rate_info(response)
        except Exception as e:
            return ComparativeTestResult(
                extra_name=extra_def.name,
                carrier=carrier,
                service_level=service_level,
                result=ComparativeResult.ERROR,
                baseline_rate_count=baseline["rate_count"],
                baseline_rate_ids=[r["id"] for r in baseline["rates"]],
                error_message=str(e)
            )

        # Compare results
        baseline_service_rates = [
            r for r in baseline["rates"]
            if r["service_level"] == service_level
        ]
        extra_service_rates = [
            r for r in extra_info["rates"]
            if r["service_level"] == service_level
        ]

        result = ComparativeTestResult(
            extra_name=extra_def.name,
            carrier=carrier,
            service_level=service_level,
            result=ComparativeResult.ERROR,  # Will be set below
            baseline_rate_count=len(baseline_service_rates),
            baseline_rate_ids=[r["id"] for r in baseline_service_rates],
            baseline_messages=baseline["messages"],
            extra_rate_count=len(extra_service_rates),
            extra_rate_ids=[r["id"] for r in extra_service_rates],
            extra_messages=extra_info["messages"]
        )

        # Determine result type
        if not extra_info["success"]:
            # Extra caused the request to fail
            result.result = ComparativeResult.EXTRA_REJECTED
            result.error_message = "; ".join(extra_info["messages"])

        elif len(extra_service_rates) == 0 and len(baseline_service_rates) > 0:
            # Extra caused service level to become unavailable
            result.result = ComparativeResult.EXTRA_REJECTED
            result.rate_availability_change = "Service level no longer available"

        elif len(extra_service_rates) > 0 and len(baseline_service_rates) > 0:
            # Both have rates - check if prices changed
            baseline_price = baseline_service_rates[0]["amount"]
            extra_price = extra_service_rates[0]["amount"]

            if abs(extra_price - baseline_price) > 0.01:
                result.result = ComparativeResult.EXTRA_MODIFIED_RATES
                result.rate_price_change = extra_price - baseline_price
            else:
                # Same price - extra might be ignored or accepted without effect
                # Check messages for any indication
                extra_mentioned = any(
                    extra_def.name.replace("_", " ").lower() in m.lower()
                    for m in extra_info["messages"]
                )
                if extra_mentioned:
                    result.result = ComparativeResult.EXTRA_ACCEPTED
                else:
                    result.result = ComparativeResult.EXTRA_IGNORED

        elif len(extra_service_rates) == 0 and len(baseline_service_rates) == 0:
            # Neither have rates for this service level
            result.result = ComparativeResult.EXTRA_IGNORED
            result.error_message = "Service level not available for test addresses"

        else:
            # Extra enabled rates that weren't available before (unlikely but possible)
            result.result = ComparativeResult.EXTRA_ACCEPTED

        return result

    async def _run_test_batch(
        self,
        client: ShippoClient,
        test_configs: list[tuple]
    ) -> list[ComparativeTestResult]:
        """Run a batch of tests in parallel"""
        tasks = [
            self.test_extra_comparative(
                client=client,
                extra_def=extra_def,
                carrier=carrier,
                service_level=service_level,
                carrier_account_id=carrier_account_id
            )
            for extra_def, carrier, service_level, carrier_account_id in test_configs
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            extra_def, carrier, service_level, _ = test_configs[i]

            if isinstance(result, Exception):
                processed_results.append(ComparativeTestResult(
                    extra_name=extra_def.name,
                    carrier=carrier,
                    service_level=service_level,
                    result=ComparativeResult.ERROR,
                    error_message=str(result)
                ))
            else:
                processed_results.append(result)

        return processed_results

    async def run_comparative_tests(
        self,
        carriers: dict[str, dict],
        carriers_filter: list[str] = None,
        service_levels_filter: list[str] = None,
        extras_filter: list[str] = None,
        max_tests: int = None
    ) -> list[ComparativeTestResult]:
        """Run comparative tests for all combinations in parallel"""

        # Build test configurations grouped by carrier/service level
        # (to efficiently share baselines)
        test_configs_by_sl = {}
        total_count = 0

        for carrier, info in carriers.items():
            if carriers_filter and carrier not in carriers_filter:
                continue

            if not info.get("active", False):
                print(f"Skipping inactive carrier: {carrier}")
                continue

            for sl in info.get("service_levels", []):
                sl_token = sl["token"]

                if service_levels_filter and sl_token not in service_levels_filter:
                    continue

                key = f"{carrier}:{sl_token}"
                test_configs_by_sl[key] = []

                for extra_def in EXTRAS_TO_TEST:
                    if extras_filter and extra_def.name not in extras_filter:
                        continue

                    test_configs_by_sl[key].append((
                        extra_def,
                        carrier,
                        sl_token,
                        info["account_id"]
                    ))
                    total_count += 1

                    if max_tests and total_count >= max_tests:
                        break

                if max_tests and total_count >= max_tests:
                    break

            if max_tests and total_count >= max_tests:
                break

        print(f"\nRunning {total_count} comparative tests with concurrency {self.concurrency}...")

        async with ShippoClient(self.api_key, self.concurrency) as client:
            # Process each service level group
            # This ensures baseline is fetched once per service level
            completed = 0
            for key, configs in test_configs_by_sl.items():
                if not configs:
                    continue

                # Clear baseline cache for new service level group
                self.baseline_cache = {}

                carrier, sl = key.split(":", 1)
                print(f"\n  Testing {carrier} - {sl} ({len(configs)} extras)...")

                results = await self._run_test_batch(client, configs)
                self.results.extend(results)

                completed += len(results)

                # Print summary for this group
                accepted = sum(1 for r in results if r.result == ComparativeResult.EXTRA_ACCEPTED)
                rejected = sum(1 for r in results if r.result == ComparativeResult.EXTRA_REJECTED)
                modified = sum(1 for r in results if r.result == ComparativeResult.EXTRA_MODIFIED_RATES)
                ignored = sum(1 for r in results if r.result == ComparativeResult.EXTRA_IGNORED)
                print(f"    ✓{accepted} $±{modified} ✗{rejected} ○{ignored}")

        return self.results

    def generate_support_matrix(self) -> dict:
        """Generate a support matrix from test results"""
        matrix = {}

        for result in self.results:
            key = f"{result.carrier}:{result.service_level}"
            if key not in matrix:
                matrix[key] = {
                    "carrier": result.carrier,
                    "service_level": result.service_level,
                    "accepted": [],
                    "rejected": [],
                    "ignored": [],
                    "modified_rates": [],
                    "baseline_failed": [],
                    "errors": []
                }

            category_map = {
                ComparativeResult.EXTRA_ACCEPTED: "accepted",
                ComparativeResult.EXTRA_REJECTED: "rejected",
                ComparativeResult.EXTRA_IGNORED: "ignored",
                ComparativeResult.EXTRA_MODIFIED_RATES: "modified_rates",
                ComparativeResult.BASELINE_FAILED: "baseline_failed",
                ComparativeResult.ERROR: "errors"
            }

            category = category_map.get(result.result, "errors")
            matrix[key][category].append({
                "extra": result.extra_name,
                "price_change": result.rate_price_change,
                "error": result.error_message
            })

        return matrix


def save_comparative_results(results: list[ComparativeTestResult], filename: str):
    """Save comparative results to JSON"""
    data = [asdict(r) for r in results]
    # Convert enum to string
    for d in data:
        d["result"] = d["result"].value if hasattr(d["result"], "value") else str(d["result"])

    with open(filename, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Results saved to {filename}")


def generate_comparative_markdown(matrix: dict) -> str:
    """Generate markdown report from support matrix"""
    md = []
    md.append("# Shippo Extras Comparative Test Report")
    md.append(f"\nGenerated: {datetime.utcnow().isoformat()}")

    md.append("\n## Legend")
    md.append("- **Accepted**: Extra was accepted and shipment created successfully")
    md.append("- **Rejected**: Extra caused the shipment to fail or service level to become unavailable")
    md.append("- **Ignored**: Extra had no visible effect (possibly unsupported or not applicable)")
    md.append("- **Modified Rates**: Extra changed the shipping rate (indicates support)")

    for key, data in sorted(matrix.items()):
        md.append(f"\n## {data['carrier']} - {data['service_level']}")

        if data["accepted"]:
            md.append("\n### ✓ Accepted Extras")
            for item in data["accepted"]:
                md.append(f"- {item['extra']}")

        if data["modified_rates"]:
            md.append("\n### $ Extras That Modify Rates")
            for item in data["modified_rates"]:
                change = f" (+${item['price_change']:.2f})" if item['price_change'] else ""
                md.append(f"- {item['extra']}{change}")

        if data["rejected"]:
            md.append("\n### ✗ Rejected Extras")
            for item in data["rejected"]:
                error = f" - {item['error'][:50]}..." if item['error'] else ""
                md.append(f"- {item['extra']}{error}")

        if data["ignored"]:
            md.append("\n### ○ Ignored/Unknown Extras")
            for item in data["ignored"]:
                md.append(f"- {item['extra']}")

    return "\n".join(md)


async def async_main(args):
    """Async main function"""
    api_key = os.environ.get("SHIPPO_API_KEY")
    if not api_key:
        print("Error: SHIPPO_API_KEY environment variable not set")
        return 1

    # Discover carriers
    from shippo_extras import ShippoExtrasTestRunner
    discovery = ShippoExtrasTestRunner(api_key, concurrency=args.concurrency)
    carriers = await discovery.discover_carriers()

    # Run comparative tests
    runner = ComparativeTestRunner(api_key, concurrency=args.concurrency)
    results = await runner.run_comparative_tests(
        carriers=carriers,
        carriers_filter=args.carriers,
        service_levels_filter=args.service_levels,
        extras_filter=args.extras,
        max_tests=args.max_tests
    )

    # Generate outputs
    save_comparative_results(results, f"{args.output}.json")

    matrix = runner.generate_support_matrix()
    with open(f"{args.output}_matrix.json", "w") as f:
        json.dump(matrix, f, indent=2)

    md_report = generate_comparative_markdown(matrix)
    with open(f"{args.output}.md", "w") as f:
        f.write(md_report)

    print(f"\nReports saved to {args.output}.*")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run comparative extras validation (async)")
    parser.add_argument("--carrier", "-c", action="append", dest="carriers")
    parser.add_argument("--service-level", "-s", action="append", dest="service_levels")
    parser.add_argument("--extra", "-e", action="append", dest="extras")
    parser.add_argument("--max-tests", "-m", type=int)
    parser.add_argument(
        "--concurrency", "-j",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Number of concurrent requests (default: {DEFAULT_CONCURRENCY})"
    )
    parser.add_argument("--output", "-o", default="shippo_comparative_results")

    args = parser.parse_args()

    exit_code = asyncio.run(async_main(args))
    exit(exit_code)
