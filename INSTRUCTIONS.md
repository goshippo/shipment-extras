# Shippo Extras Discovery Test Suite - Complete Instructions

## Overview

This test suite empirically discovers which shipment extras are supported by each carrier and service level in the Shippo API. Since the Shippo documentation and MCP schema don't provide a complete carrier-to-extras mapping, this suite tests each combination and builds a comprehensive capability matrix.

---

## Quick Start

```bash
# 1. Install dependencies (requires uv)
make install-dev

# 2. Set your API key
export SHIPPO_API_KEY="shippo_test_xxxxx"  # Use test key first

# 3. Verify your carriers are connected
make list-carriers

# 4. Run a quick test to validate setup
make run-discovery-quick

# 5. Run full test suite
make run-discovery
```

---

## Prerequisites

### 1. Install uv

This project uses [uv](https://docs.astral.sh/uv/) for fast, reliable dependency management.

```bash
# Install uv (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv

# Verify installation
uv --version
```

### 2. Python Environment

```bash
# Python 3.11+ required (for async features)
python --version

# Install dependencies via Makefile
make install-dev

# Or install directly with uv
uv sync
```

**Dependencies:**
- `httpx>=0.25.0` - Async HTTP client with connection pooling
- `pytest>=7.0.0` - Test framework (dev)
- `pytest-asyncio>=0.21.0` - Async test support (dev)
- `ruff>=0.1.0` - Linting and formatting (dev)

### 3. Shippo API Key

Get your API key from [Shippo Dashboard](https://apps.goshippo.com/settings/api):

```bash
# For testing (recommended to start)
export SHIPPO_API_KEY="shippo_test_xxxxxxxxxxxxxxxxxxxxx"

# For production data
export SHIPPO_API_KEY="shippo_live_xxxxxxxxxxxxxxxxxxxxx"
```

### 4. Connected Carrier Accounts

The tests only work for carriers you have connected in your Shippo account:

1. Go to [Shippo Carriers](https://apps.goshippo.com/settings/carriers)
2. Add the carriers you want to test
3. Ensure they are marked as "Active"

---

## Makefile Targets

The project includes a comprehensive Makefile for development workflow automation:

### Setup

```bash
make install        # Install runtime dependencies only
make install-dev    # Install with development dependencies
make sync           # Sync dependencies from lockfile
```

### Quality Assurance

```bash
make lint           # Run ruff linter
make format         # Format code with ruff
make test           # Run async behavior test suite
make test-cov       # Run tests with coverage
make quality        # Run all quality checks (lint + test)
```

### Discovery Tests

```bash
make list-carriers  # List connected carrier accounts
make list-extras    # List all testable extras
make run-discovery  # Run basic discovery tests
make run-comparative # Run comparative analysis
make run-analyzer   # Run service level analyzer
```

### Custom Runs

```bash
# Test specific carrier
make run-carrier CARRIER=usps

# Run with higher concurrency (faster)
make run-fast CONCURRENCY=20
```

---

## Test Modules Explained

### Module 1: `shippo_extras.py` - Basic Discovery

**Purpose**: Quickly determine if each extra is accepted or rejected for each carrier/service level.

**How it works**:
1. Creates shipments with a specific extra (async parallel requests)
2. Checks if the API returns rates or errors
3. Categorizes the result

**Best for**: Initial discovery, quick validation

```bash
# Full run
uv run python src/shippo_extras.py

# With concurrency control (default: 5)
uv run python src/shippo_extras.py -j 10  # 10 parallel requests

# See all available extras
uv run python src/shippo_extras.py --list-extras

# See your connected carriers
uv run python src/shippo_extras.py --list-carriers

# Validate specific carriers
uv run python src/shippo_extras.py -c usps -c fedex -c ups

# Validate specific service levels
uv run python src/shippo_extras.py -c fedex -s fedex_ground -s fedex_2_day

# Validate specific extras
uv run python src/shippo_extras.py -e signature_confirmation -e insurance_shippo

# Limit number of validations (for quick check)
uv run python src/shippo_extras.py --max-tests 50

# Custom output filename
uv run python src/shippo_extras.py -o my_company_results
```

**Output files**:
| File | Description |
|------|-------------|
| `*_raw.json` | Every test result with full details |
| `*_report.json` | Aggregated report by carrier and extra |
| `*_report.md` | Human-readable markdown summary |

---

### Module 2: `comparative_runner.py` - Detailed Analysis

**Purpose**: Distinguish between "supported", "rejected", and "silently ignored" extras.

**How it works**:
1. Creates a **baseline** shipment without any extras
2. Creates shipments **with** each extra (async parallel)
3. Compares the two responses to determine actual support

**Best for**: Accurate capability mapping, finding extras that affect rates

```bash
# Full comparative run
uv run python src/comparative_runner.py

# With concurrency control
uv run python src/comparative_runner.py -j 10

# With filters
uv run python src/comparative_runner.py -c ups -c fedex

# Limit validations
uv run python src/comparative_runner.py --max-tests 100

# Custom output
uv run python src/comparative_runner.py -o comparative_results
```

**Result types explained**:

| Result | What it means | Confidence |
|--------|---------------|------------|
| `EXTRA_ACCEPTED` | Extra was recognized, shipment created | High |
| `EXTRA_REJECTED` | Extra caused failure or service unavailability | High |
| `EXTRA_MODIFIED_RATES` | Extra changed the price (strong support indicator) | Very High |
| `EXTRA_IGNORED` | No visible difference from baseline | Low (could be supported but no effect) |
| `BASELINE_FAILED` | Couldn't create baseline shipment | N/A |

**Output files**:
| File | Description |
|------|-------------|
| `*.json` | Detailed comparative results |
| `*_matrix.json` | Support matrix organized by carrier/service level |
| `*.md` | Human-readable markdown report |

---

### Module 3: `service_level_analyzer.py` - Service Level Granularity

**Purpose**: Find patterns in extra support across service levels (e.g., "Saturday delivery only works with express services").

**How it works**:
1. Categorizes service levels (express, ground, economy, etc.)
2. Tests extras against each service level (async parallel)
3. Identifies extras that vary by service level within a carrier

**Best for**: Understanding service-level-specific restrictions

```bash
# Full analysis
uv run python analysis/service_level_analyzer.py

# With concurrency control
uv run python analysis/service_level_analyzer.py -j 10

# Specific carrier
uv run python analysis/service_level_analyzer.py -c fedex

# Custom output
uv run python analysis/service_level_analyzer.py -o service_analysis
```

**Output files**:
| File | Description |
|------|-------------|
| `*_results.json` | All results with service category tags |
| `*_matrices.json` | Per-service-level support matrices |
| `*_report.md` | Cross-service-level analysis |

---

## Async Architecture

### Concurrency Control

All test scripts use async HTTP with configurable concurrency:

```bash
# Default: 5 concurrent requests
uv run python src/shippo_extras.py

# Increase for faster execution
uv run python src/shippo_extras.py -j 20

# Decrease if hitting rate limits
uv run python src/shippo_extras.py -j 2
```

### Rate Limiting

The test suite includes intelligent rate limiting:

- **Semaphore-based concurrency**: Limits parallel requests
- **Header monitoring**: Tracks `X-RateLimit-Remaining` headers
- **Proactive waiting**: Slows down when approaching limits
- **Automatic retry**: Handles 429 responses with exponential backoff

### Race Condition Protection

Shared resources (like baseline caches) are protected with `asyncio.Lock`:

```python
async with self._baseline_lock:
    if cache_key in self.baseline_cache:
        return self.baseline_cache[cache_key]
```

---

## Complete Workflow

### Step 1: Initial Discovery

Run basic tests to see what's available:

```bash
# List your carriers first
make list-carriers

# Quick run with one carrier
uv run python src/shippo_extras.py -c usps --max-tests 20

# Review results
cat shippo_extras_results_report.md
```

### Step 2: Detailed Analysis

Run comparative tests for accurate results:

```bash
# Run comparative analysis
uv run python src/comparative_runner.py -c usps -c fedex -c ups

# Review the support matrix
cat shippo_comparative_results.md
```

### Step 3: Service Level Analysis

Find service-level-specific patterns:

```bash
# Analyze service levels
uv run python analysis/service_level_analyzer.py

# Review patterns
cat shippo_service_level_report.md
```

### Step 4: Build Your Capability Matrix

Use the results to build your abstraction layer:

```python
import json

# Load comparative results (most accurate)
with open("shippo_comparative_results_matrix.json") as f:
    matrix = json.load(f)

# Build your capability map
carrier_capabilities = {}

for key, data in matrix.items():
    carrier = data["carrier"]
    service_level = data["service_level"]

    if carrier not in carrier_capabilities:
        carrier_capabilities[carrier] = {}

    carrier_capabilities[carrier][service_level] = {
        "supported_extras": [
            e["extra"] for e in data["accepted"]
        ] + [
            e["extra"] for e in data["modified_rates"]
        ],
        "unsupported_extras": [
            e["extra"] for e in data["rejected"]
        ],
        "unknown_extras": [
            e["extra"] for e in data["ignored"]
        ]
    }

# Save for your application
with open("carrier_capabilities.json", "w") as f:
    json.dump(carrier_capabilities, f, indent=2)
```

---

## Test Addresses

The tests use these addresses by default:

**From (San Francisco)**:
```
215 Clayton St
San Francisco, CA 94117
```

**To Domestic (Washington DC)**:
```
1600 Pennsylvania Avenue NW
Washington, DC 20500
```

**To International (London)**:
```
10 Downing Street
London, SW1A 2AA, UK
```

To modify these, edit the constants in `shippo_extras.py`:
- `TEST_ADDRESS_FROM`
- `TEST_ADDRESS_TO`
- `TEST_ADDRESS_INTERNATIONAL`

---

## Interpreting Results

### High Confidence Support

An extra is **definitely supported** if:
- `EXTRA_MODIFIED_RATES` - The rate changed when the extra was added
- `EXTRA_ACCEPTED` with explicit mention in API messages

### High Confidence Not Supported

An extra is **definitely not supported** if:
- `EXTRA_REJECTED` - API returned an error specifically about the extra
- Service level became unavailable only when extra was added

### Low Confidence / Needs Investigation

An extra has **unknown support** if:
- `EXTRA_IGNORED` - No change from baseline (could be supported but inactive, or unsupported)
- `INVALID_VALUE` - The extra exists but test values may be wrong

For "ignored" extras, you may need to:
1. Try different test values
2. Test with actual shipment content (e.g., alcohol extras need alcohol shipments)
3. Check carrier documentation directly

---

## Extras Reference

### Signature Confirmation

| Extra Name | Value | Carriers |
|------------|-------|----------|
| `signature_confirmation` | `STANDARD` | Most carriers |
| `signature_confirmation_adult` | `ADULT` | Most carriers |
| `signature_confirmation_certified` | `CERTIFIED` | USPS only |
| `signature_confirmation_indirect` | `INDIRECT` | FedEx only |
| `signature_confirmation_carrier` | `CARRIER_CONFIRMATION` | Deutsche Post |

### Insurance

| Extra Name | Value | Notes |
|------------|-------|-------|
| `insurance_shippo` | `{amount, currency, content}` | XCover 3rd party |
| `insurance_fedex` | `{..., provider: "FEDEX"}` | FedEx declared value |
| `insurance_ups` | `{..., provider: "UPS"}` | UPS declared value |
| `insurance_ontrac` | `{..., provider: "ONTRAC"}` | OnTrac declared value |

### COD (Cash on Delivery)

| Extra Name | Value | Carriers |
|------------|-------|----------|
| `cod_any` | `{amount, currency, payment_method: "ANY"}` | UPS |
| `cod_cash` | `{..., payment_method: "CASH"}` | UPS |
| `cod_secured` | `{..., payment_method: "SECURED_FUNDS"}` | UPS |

### Billing

| Extra Name | Value | Carriers |
|------------|-------|----------|
| `billing_recipient` | `{type: "RECIPIENT"}` | UPS, FedEx, DHL Germany |
| `billing_third_party` | `{type: "THIRD_PARTY", account, zip, country}` | UPS, FedEx, DHL Germany |
| `billing_collect` | `{type: "COLLECT"}` | UPS, FedEx |

### Hazmat / Special Handling

| Extra Name | Value | Carriers |
|------------|-------|----------|
| `alcohol_consumer` | `{contains_alcohol: true, recipient_type: "consumer"}` | FedEx, UPS |
| `alcohol_licensee` | `{contains_alcohol: true, recipient_type: "licensee"}` | FedEx, UPS |
| `dry_ice` | `{contains_dry_ice: true, weight: "5"}` | FedEx, Veho, UPS |
| `dangerous_goods` | `{contains: true}` | USPS |
| `dangerous_goods_lithium` | `{lithium_batteries: {contains: true}}` | USPS |
| `dangerous_goods_code_*` | `"01"` through `"09"` | DHL eCommerce |

### Delivery Options

| Extra Name | Value | Notes |
|------------|-------|-------|
| `saturday_delivery` | `true` | Usually express only |
| `authority_to_leave` | `true` | |
| `delivery_instructions` | `"Leave at back door"` | |
| `carbon_neutral` | `true` | |
| `premium` | `true` | |
| `qr_code_requested` | `true` | |
| `bypass_address_validation` | `true` | |

### Reference Fields

| Extra Name | Value | Carriers |
|------------|-------|----------|
| `reference_1` | `"REF-001"` | Most carriers |
| `reference_2` | `"REF-002"` | Most carriers |
| `customer_reference` | `{value: "CUST-REF"}` | FedEx, UPS |
| `po_number` | `{value: "PO-12345"}` | FedEx, UPS |
| `invoice_number` | `{value: "INV-12345"}` | FedEx, UPS |
| `dept_number` | `{value: "DEPT-001"}` | FedEx, UPS |
| `rma_number` | `{value: "RMA-12345"}` | FedEx, UPS |

### Return Options

| Extra Name | Value | Notes |
|------------|-------|-------|
| `is_return` | `true` | |
| `return_service_print_and_mail` | `"PRINT_AND_MAIL"` | |
| `return_service_electronic` | `"ELECTRONIC_LABEL"` | |

### Carrier-Specific

| Extra Name | Value | Carrier |
|------------|-------|---------|
| `ancillary_endorsement_forwarding` | `"FORWARDING_SERVICE_REQUESTED"` | DHL eCommerce |
| `ancillary_endorsement_return` | `"RETURN_SERVICE_REQUESTED"` | DHL eCommerce |
| `preferred_delivery_timeframe` | `"10001200"` | DHL Germany |
| `lasership_declared_value` | `"100.00"` | LaserShip |
| `lasership_attrs_alcohol` | `["Alcohol"]` | LaserShip |
| `lasership_attrs_perishable` | `["Perishable"]` | LaserShip |

---

## Troubleshooting

### "Authentication failed" error

```bash
# Verify your API key is set
echo $SHIPPO_API_KEY

# Should start with "shippo_test_" or "shippo_live_"
```

### "No carriers found"

1. Check that you have carriers connected in Shippo dashboard
2. Ensure carriers are marked as "Active"
3. Verify API key has access to those carriers

### "Rate limited" errors

```bash
# Reduce concurrency
uv run python src/shippo_extras.py -j 2

# Or reduce scope
uv run python src/shippo_extras.py --max-tests 20

# Wait a few minutes and retry
```

### "Service level not available"

Some service levels aren't available for test addresses. This is normal - the test will skip those combinations.

### Tests taking too long

```bash
# Increase concurrency (if not hitting rate limits)
uv run python src/shippo_extras.py -j 15

# Validate fewer carriers
uv run python src/shippo_extras.py -c usps

# Validate fewer extras
uv run python src/shippo_extras.py -e signature_confirmation -e insurance_shippo

# Limit total validations
uv run python src/shippo_extras.py --max-tests 100
```

---

## Extending the Test Suite

### Adding New Extras

Edit `shippo_extras.py` and add to `EXTRAS_TO_TEST`:

```python
ExtraDefinition(
    name="my_new_extra",
    category=ExtraCategory.DELIVERY,
    test_value={"some": "value"},
    description="Description of the extra",
    documented_carriers=["usps", "fedex"]  # Optional
)
```

### Custom Test Addresses

Edit the address constants at the top of `shippo_extras.py`:

```python
TEST_ADDRESS_FROM = {
    "name": "Your Company",
    "street1": "123 Your Street",
    # ...
}
```

### Custom Parcel Dimensions

Edit `TEST_PARCEL` in `shippo_extras.py`:

```python
TEST_PARCEL = {
    "length": "12",
    "width": "10",
    "height": "8",
    "distance_unit": "in",
    "weight": "5",
    "mass_unit": "lb"
}
```

---

## Output Files Summary

| Module | Output Files |
|--------|--------------|
| `shippo_extras.py` | `*_raw.json`, `*_report.json`, `*_report.md` |
| `comparative_runner.py` | `*.json`, `*_matrix.json`, `*.md` |
| `service_level_analyzer.py` | `*_results.json`, `*_matrices.json`, `*_report.md` |

---

## Running Tests

### Async Behavior Tests

Verify the async implementation works correctly:

```bash
# Run all async tests
make test

# Run with verbose output
uv run pytest test/test_async_behavior.py -v

# Run specific test class
uv run pytest test/test_async_behavior.py::TestRaceConditionProtection -v

# Run with coverage
make test-cov
```

---

## Support

For issues with:
- **This test suite**: Review the code and adapt as needed
- **Shippo API**: Check [Shippo Documentation](https://docs.goshippo.com/)
- **Carrier-specific questions**: Contact the carrier directly

---

## License

This test suite is provided as-is for integration development purposes.
