"""
Live Integration Tests for Shippo Extras Discovery Suite

These tests make REAL API calls to the Shippo API and require:
1. A valid SHIPPO_API_KEY environment variable
2. At least one active carrier account connected

Run with:
    pytest test/test_live_integration.py -v

Skip in CI:
    pytest test/ --ignore=test/test_live_integration.py

Note: These tests use the Shippo TEST mode API, so no actual charges occur.
"""

import os
import sys
import pytest
import asyncio

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from shippo_extras import (
    ShippoClient,
    ShippoExtrasTestRunner,
    ExtraDefinition,
    ExtraCategory,
    ExtraResult,
    EXTRAS_TO_TEST,
    TEST_ADDRESS_FROM,
    TEST_ADDRESS_TO,
    TEST_PARCEL,
)


# =============================================================================
# Fixtures
# =============================================================================

def get_api_key() -> str | None:
    """Get API key from environment"""
    return os.environ.get("SHIPPO_API_KEY")


@pytest.fixture
def api_key():
    """Fixture that skips if no API key"""
    key = get_api_key()
    if not key:
        pytest.skip("SHIPPO_API_KEY environment variable not set")
    return key


@pytest.fixture
def runner(api_key):
    """Create a test runner instance"""
    return ShippoExtrasTestRunner(api_key, concurrency=3)


# =============================================================================
# Test: API Connectivity
# =============================================================================

class TestAPIConnectivity:
    """Basic API connectivity tests"""

    @pytest.mark.asyncio
    async def test_client_can_connect(self, api_key):
        """Test that we can connect to the Shippo API"""
        async with ShippoClient(api_key, concurrency=3) as client:
            # Make a simple request to verify connectivity
            response = await client._request("GET", "/carrier_accounts?results=1")

            assert response["status_code"] in [200, 401], \
                f"Unexpected status: {response['status_code']}"

            if response["status_code"] == 401:
                pytest.fail("API key is invalid - authentication failed")

            # Should have valid response structure
            assert "data" in response
            print(f"✓ API connection successful")

    @pytest.mark.asyncio
    async def test_list_carrier_accounts(self, api_key):
        """Test that we can list carrier accounts"""
        async with ShippoClient(api_key, concurrency=3) as client:
            accounts = await client.list_carrier_accounts(service_levels=True)

            assert isinstance(accounts, list), "Expected list of accounts"
            print(f"✓ Found {len(accounts)} carrier accounts")

            # Print summary
            for acc in accounts[:5]:  # First 5 only
                carrier = acc.get("carrier", "unknown")
                active = acc.get("active", False)
                service_levels = acc.get("service_levels", [])
                print(f"  - {carrier}: {'Active' if active else 'Inactive'}, {len(service_levels)} service levels")


# =============================================================================
# Test: Carrier Discovery
# =============================================================================

class TestCarrierDiscovery:
    """Test carrier and service level discovery"""

    @pytest.mark.asyncio
    async def test_discover_carriers(self, runner):
        """Test carrier discovery functionality"""
        carriers = await runner.discover_carriers()

        assert isinstance(carriers, dict), "Expected dict of carriers"
        assert len(carriers) > 0, "No carriers found - add carriers in Shippo dashboard"

        print(f"✓ Discovered {len(carriers)} carriers:")
        for carrier, info in carriers.items():
            active = "Active" if info["active"] else "Inactive"
            sl_count = len(info["service_levels"])
            print(f"  - {carrier}: {active}, {sl_count} service levels")

    @pytest.mark.asyncio
    async def test_carrier_has_service_levels(self, runner):
        """Test that at least one carrier has service levels"""
        carriers = await runner.discover_carriers()

        carriers_with_sl = [
            c for c, info in carriers.items()
            if len(info["service_levels"]) > 0 and info["active"]
        ]

        assert len(carriers_with_sl) > 0, \
            "No active carriers with service levels found"

        print(f"✓ Found {len(carriers_with_sl)} carriers with service levels")


# =============================================================================
# Test: Shipment Creation
# =============================================================================

class TestShipmentCreation:
    """Test shipment creation with and without extras"""

    @pytest.mark.asyncio
    async def test_create_basic_shipment(self, api_key):
        """Test creating a basic shipment without extras"""
        async with ShippoClient(api_key, concurrency=3) as client:
            response = await client.create_shipment(
                address_from=TEST_ADDRESS_FROM,
                address_to=TEST_ADDRESS_TO,
                parcel=TEST_PARCEL
            )

            assert response["status_code"] in [200, 201], \
                f"Failed to create shipment: {response['data']}"

            data = response["data"]
            rates = data.get("rates", [])

            print(f"✓ Created shipment, got {len(rates)} rates")

            # Print first few rates
            for rate in rates[:3]:
                carrier = rate.get("provider", "unknown")
                service = rate.get("servicelevel", {}).get("token", "unknown")
                amount = rate.get("amount", "?")
                print(f"  - {carrier}/{service}: ${amount}")

    @pytest.mark.asyncio
    async def test_create_shipment_with_signature(self, api_key):
        """Test creating a shipment with signature confirmation"""
        async with ShippoClient(api_key, concurrency=3) as client:
            response = await client.create_shipment(
                address_from=TEST_ADDRESS_FROM,
                address_to=TEST_ADDRESS_TO,
                parcel=TEST_PARCEL,
                extra={"signature_confirmation": "STANDARD"}
            )

            # Should either succeed or return an error about the extra
            assert response["status_code"] in [200, 201, 400], \
                f"Unexpected status: {response['status_code']}"

            data = response["data"]

            if response["status_code"] in [200, 201]:
                rates = data.get("rates", [])
                print(f"✓ Signature confirmation accepted, got {len(rates)} rates")
            else:
                print(f"✓ Signature confirmation rejected: {data}")

    @pytest.mark.asyncio
    async def test_create_shipment_with_insurance(self, api_key):
        """Test creating a shipment with insurance"""
        async with ShippoClient(api_key, concurrency=3) as client:
            response = await client.create_shipment(
                address_from=TEST_ADDRESS_FROM,
                address_to=TEST_ADDRESS_TO,
                parcel=TEST_PARCEL,
                extra={
                    "insurance": {
                        "amount": "100",
                        "currency": "USD",
                        "content": "Test merchandise"
                    }
                }
            )

            assert response["status_code"] in [200, 201, 400], \
                f"Unexpected status: {response['status_code']}"

            data = response["data"]

            if response["status_code"] in [200, 201]:
                rates = data.get("rates", [])
                print(f"✓ Insurance accepted, got {len(rates)} rates")
            else:
                print(f"✓ Insurance handling: {data}")


# =============================================================================
# Test: Extras Testing Flow
# =============================================================================

class TestExtrasFlow:
    """Test the extras testing workflow"""

    @pytest.mark.asyncio
    async def test_single_extra_test(self, api_key):
        """Test running a single extra test"""
        runner = ShippoExtrasTestRunner(api_key, concurrency=3)
        carriers = await runner.discover_carriers()

        # Find an active carrier with service levels
        active_carrier = None
        for carrier, info in carriers.items():
            if info["active"] and len(info["service_levels"]) > 0:
                active_carrier = (carrier, info)
                break

        if not active_carrier:
            pytest.skip("No active carriers with service levels")

        carrier_name, carrier_info = active_carrier
        service_level = carrier_info["service_levels"][0]["token"]

        # Test signature confirmation
        extra_def = ExtraDefinition(
            name="signature_confirmation",
            category=ExtraCategory.SIGNATURE,
            test_value="STANDARD",
            description="Standard signature confirmation"
        )

        async with ShippoClient(api_key, concurrency=3) as client:
            result = await runner.test_extra(
                client=client,
                extra_def=extra_def,
                carrier=carrier_name,
                service_level=service_level,
                carrier_account_id=carrier_info["account_id"]
            )

        assert result is not None
        assert result.extra_name == "signature_confirmation"
        assert result.carrier == carrier_name
        assert result.service_level == service_level
        assert result.result in ExtraResult

        print(f"✓ Tested signature_confirmation on {carrier_name}/{service_level}")
        print(f"  Result: {result.result.value}")
        if result.error_message:
            print(f"  Message: {result.error_message}")

    @pytest.mark.asyncio
    async def test_limited_run(self, runner):
        """Test running a limited number of tests"""
        # Run just 5 tests to verify the flow works
        results = await runner.run_all_tests(max_tests=5)

        assert isinstance(results, list), "Expected list of results"
        assert len(results) <= 5, f"Expected <=5 results, got {len(results)}"

        print(f"✓ Completed {len(results)} tests")

        # Count by result type
        by_result = {}
        for r in results:
            key = r.result.value
            by_result[key] = by_result.get(key, 0) + 1

        for result_type, count in by_result.items():
            print(f"  - {result_type}: {count}")


# =============================================================================
# Test: Report Generation
# =============================================================================

class TestReportGeneration:
    """Test report generation functionality"""

    @pytest.mark.asyncio
    async def test_generate_report(self, runner):
        """Test report generation after running tests"""
        # Run a few tests
        await runner.run_all_tests(max_tests=3)

        # Generate report
        report = runner.generate_report()

        assert "generated_at" in report
        assert "total_tests" in report
        assert "summary" in report
        assert "by_carrier" in report
        assert "by_extra" in report
        assert "capability_matrix" in report

        print(f"✓ Generated report with {report['total_tests']} tests")
        print(f"  Summary: {report['summary']}")


# =============================================================================
# Test: Rate Limiting
# =============================================================================

class TestRateLimiting:
    """Test rate limit handling"""

    @pytest.mark.asyncio
    async def test_concurrent_requests_dont_exceed_limit(self, api_key):
        """Test that concurrent requests are properly throttled"""
        async with ShippoClient(api_key, concurrency=3) as client:
            # Make several concurrent requests
            tasks = [
                client._request("GET", "/carrier_accounts?results=1")
                for _ in range(5)
            ]

            results = await asyncio.gather(*tasks)

            # All should succeed (no rate limit errors)
            success_count = sum(1 for r in results if r["status_code"] == 200)

            # Allow for some failures but most should succeed
            assert success_count >= 3, \
                f"Too many failures: {5 - success_count}/5"

            print(f"✓ Completed {success_count}/5 concurrent requests successfully")


# =============================================================================
# Test: Error Handling
# =============================================================================

class TestErrorHandling:
    """Test error handling scenarios"""

    @pytest.mark.asyncio
    async def test_invalid_carrier_account(self, api_key):
        """Test handling of invalid carrier account ID"""
        async with ShippoClient(api_key, concurrency=3) as client:
            response = await client.create_shipment(
                address_from=TEST_ADDRESS_FROM,
                address_to=TEST_ADDRESS_TO,
                parcel=TEST_PARCEL,
                carrier_accounts=["invalid_account_id"]
            )

            # Should get an error or empty rates
            data = response["data"]

            if response["status_code"] in [200, 201]:
                # May return empty rates for invalid carrier
                rates = data.get("rates", [])
                print(f"✓ Invalid carrier handled gracefully, {len(rates)} rates returned")
            else:
                print(f"✓ Invalid carrier rejected: status {response['status_code']}")

    @pytest.mark.asyncio
    async def test_invalid_extra_value(self, api_key):
        """Test handling of invalid extra values"""
        async with ShippoClient(api_key, concurrency=3) as client:
            response = await client.create_shipment(
                address_from=TEST_ADDRESS_FROM,
                address_to=TEST_ADDRESS_TO,
                parcel=TEST_PARCEL,
                extra={"signature_confirmation": "INVALID_VALUE_XYZ"}
            )

            # Should get an error response
            assert response["status_code"] in [200, 201, 400], \
                f"Unexpected status: {response['status_code']}"

            if response["status_code"] == 400:
                print(f"✓ Invalid extra value correctly rejected")
            else:
                print(f"✓ Invalid extra value handled (status {response['status_code']})")


# =============================================================================
# Run Configuration
# =============================================================================

if __name__ == "__main__":
    # Run with verbose output
    pytest.main([__file__, "-v", "-s", "--tb=short"])
