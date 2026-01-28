# Shippo Extras Discovery Suite

Empirical testing suite to discover which shipment extras are supported by each carrier and service level in the Shippo API.

## Overview

This project originated from a technical discovery call with **Ordoro**, a Shippo partner, to determine which shipment extras should be available for each carrier and service level. The existing API documentation and MCP schema lacked comprehensive carrier-to-extras mappings, making it difficult for partners to build accurate shipping UIs and construct valid API requests.

This suite empirically tests every carrier/service/extra combination and produces actionable documentation that can be used to:
- Inform partner integrations (like Ordoro's)
- Update the Shippo API swagger specification
- Improve developer experience with accurate capability matrices

## Quick Start

```bash
# 1. Clone and install dependencies
git clone <repo-url>
cd shipment-extras
make install-dev

# 2. Set your API key
export SHIPPO_API_KEY="shippo_test_xxxxx"

# 3. List connected carriers
make list-carriers

# 4. Run a quick test
make run-discovery-quick

# 5. Run full discovery suite
make run-discovery
```

## Development Setup

### Requirements

- **Python**: 3.11+ (required for async features)
- **uv**: Fast Python package manager ([install uv](https://docs.astral.sh/uv/getting-started/installation/))
- **API Key**: Shippo test or live API key with connected carriers

### Installation

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install runtime dependencies only
make install

# Install with development dependencies (includes testing tools)
make install-dev

# Sync dependencies from lockfile
make sync
```

### Environment Configuration

```bash
# Required: Set your Shippo API key
export SHIPPO_API_KEY="shippo_test_xxxxxxxxxxxxxxxxxxxxx"

# Optional: Add to ~/.zshrc or ~/.profile for persistence
echo 'export SHIPPO_API_KEY="shippo_test_xxxxx"' >> ~/.zshrc
```

### Connecting Carriers

The tests only work for carriers you have connected in your Shippo account:

1. Go to [Shippo Carriers](https://apps.goshippo.com/settings/carriers)
2. Add the carriers you want to test
3. Ensure they are marked as "Active"

## Project Structure

```
shipment-extras/
├── README.md                    # This file
├── INSTRUCTIONS.md              # Detailed usage instructions
├── Makefile                     # Development workflow automation
├── pyproject.toml               # Project metadata and dependencies (uv)
├── uv.lock                      # Locked dependencies
├── pytest.ini                   # Pytest configuration
│
├── src/                         # Main source modules
│   ├── shippo_extras.py         # Core extras discovery (async)
│   └── comparative_runner.py    # Comparative analysis runner (async)
│
├── test/                        # Unit tests
│   └── test_async_behavior.py   # Async behavior unit tests
│
├── analysis/                    # Results and analysis
│   ├── service_level_analyzer.py           # Service-level pattern analyzer (async)
│   ├── split_report.py                     # Report splitting utility
│   ├── shippo_extras_results_raw.json      # Raw test results
│   ├── shippo_extras_results_report.json   # Aggregated report
│   ├── shippo_extras_results_report.md     # Human-readable summary
│   │
│   └── carrier_reports/                    # Per-carrier analysis
│       ├── usps_report.md
│       ├── ups_report.md
│       └── ...
│
└── swagger/                     # Swagger spec and update materials
    ├── swagger.yaml             # Shippo API spec reference
    │
    └── swagger_update_prompts/  # Prompts for updating swagger spec
        ├── usps_swagger_prompt.md
        └── ...
```

## Usage

### Makefile Targets

```bash
# Setup
make install          # Install runtime dependencies
make install-dev      # Install with development dependencies
make sync             # Sync dependencies from lockfile

# Quality Assurance
make lint             # Run ruff linter
make format           # Format code with ruff
make test             # Run async behavior test suite
make quality          # Run all quality checks

# Discovery Tests
make list-carriers    # List connected carrier accounts
make list-extras      # List all testable extras
make run-discovery    # Run basic discovery tests
make run-comparative  # Run comparative analysis
make run-analyzer     # Run service level analyzer

# Custom runs
make run-carrier CARRIER=usps     # Test specific carrier
make run-fast CONCURRENCY=20      # Run with higher concurrency
```

### Command Line Options

All test scripts support the following options:

```bash
# Concurrency control (async parallel requests)
uv run python src/shippo_extras.py -j 10  # 10 concurrent requests (default: 5)

# Filter by carrier
uv run python src/shippo_extras.py -c usps -c fedex

# Filter by service level
uv run python src/shippo_extras.py -c fedex -s fedex_ground -s fedex_2_day

# Filter by extra
uv run python src/shippo_extras.py -e signature_confirmation -e insurance_shippo

# Limit test count
uv run python src/shippo_extras.py --max-tests 50

# Custom output filename
uv run python src/shippo_extras.py -o my_results
```

## Testing

### Async Behavior Tests

The test suite includes comprehensive tests for async behavior and race condition handling:

```bash
# Run async tests
make test

# Run with coverage
make test-cov

# Run specific test class
uv run pytest test/test_async_behavior.py::TestRaceConditionProtection -v
```

### Test Categories

| Category | Tests | Purpose |
|----------|-------|---------|
| Async Client Basics | 2 | Context manager, semaphore limiting |
| Rate Limiting | 2 | Retry logic, proactive waiting |
| Race Condition Protection | 2 | Cache locking, non-blocking parallel keys |
| Result Consistency | 3 | Exception handling, order preservation |
| Semaphore Under Load | 3 | Fairness, no deadlock, high contention |
| Lock Behavior | 2 | Mutual exclusion, no corruption |
| Integration | 1 | Full mock test run |
| Stress Tests | 2 | 500 concurrent tasks, rapid cache access |

## How We Tested

### Evaluation Methodology

Each shipment extra is evaluated through a multi-stage testing process designed to determine not just whether an extra is accepted, but whether it actually affects the shipment.

#### Stage 1: Discovery Testing (`shippo_extras.py`)

Creates shipments with each extra and analyzes the API response:

```
┌─────────────────────┐     ┌─────────────┐     ┌──────────────────┐
│ Shipment + Extra    │────▶│ Shippo API  │────▶│ Response Analysis│
└─────────────────────┘     └─────────────┘     └──────────────────┘
                                                        │
                           ┌────────────────────────────┼────────────────────────────┐
                           ▼                            ▼                            ▼
                    ┌─────────────┐            ┌─────────────┐            ┌─────────────────┐
                    │  ACCEPTED   │            │  REJECTED   │            │     ERROR       │
                    │ Rates exist │            │  API Error  │            │ Service N/A     │
                    └─────────────┘            └─────────────┘            └─────────────────┘
```

#### Stage 2: Comparative Testing (`comparative_runner.py`)

Creates a **baseline shipment without extras**, then compares it to shipments **with** each extra to detect actual support vs. silent ignoring:

```
┌─────────────────────┐                    ┌─────────────────────┐
│ Baseline Shipment   │                    │ Shipment + Extra    │
│ (no extras)         │                    │                     │
└─────────┬───────────┘                    └─────────┬───────────┘
          │                                          │
          ▼                                          ▼
┌─────────────────────┐                    ┌─────────────────────┐
│ Baseline Response   │◀───── COMPARE ─────▶│ Extra Response      │
└─────────────────────┘                    └─────────────────────┘
                                                    │
         ┌──────────────────────────────────────────┼──────────────────────────────────────────┐
         ▼                                          ▼                                          ▼
  ┌─────────────┐                           ┌─────────────┐                           ┌─────────────┐
  │ RATES SAME  │                           │RATES DIFFER │                           │ EXTRA FAILED│
  │ = IGNORED   │                           │= MODIFIED   │                           │ = REJECTED  │
  └─────────────┘                           └─────────────┘                           └─────────────┘
```

#### Stage 3: Service Level Analysis (`service_level_analyzer.py`)

Categorizes service levels (express, ground, economy) and identifies patterns like "Saturday delivery only works with express services."

### Validation Types

| Result | What Happens | Confidence | Interpretation |
|--------|--------------|------------|----------------|
| `EXTRA_ACCEPTED` | API accepts request, returns rates | **High** | Extra is recognized by the carrier |
| `EXTRA_REJECTED` | API returns error mentioning the extra | **High** | Extra is explicitly not supported |
| `EXTRA_MODIFIED_RATES` | Rate amounts differ from baseline | **Very High** | Extra is actively applied (e.g., signature adds $2.50) |
| `EXTRA_IGNORED` | Response identical to baseline | **Low** | Extra may be unsupported, or supported but with no visible effect |
| `BASELINE_FAILED` | Baseline shipment couldn't be created | **N/A** | Service level not available for test route |

## Architecture

### Async HTTP Client

All test scripts use an async HTTP client (`httpx.AsyncClient`) with:

- **Concurrency control**: `asyncio.Semaphore` limits parallel requests (default: 5)
- **Rate limiting**: Monitors `X-RateLimit-*` headers and 429 responses
- **Automatic retry**: Retries on rate limit with exponential backoff
- **Connection pooling**: Efficient connection reuse

### Race Condition Protection

Shared resources (baseline caches) are protected with `asyncio.Lock`:

```python
async with self._baseline_lock:
    if cache_key in self.baseline_cache:
        return self.baseline_cache[cache_key]
```

### Parallel Execution

Tests run in parallel using `asyncio.gather()`:

```python
tasks = [test_extra(e) for e in extras]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

## Test Data

- **Origin**: San Francisco, CA (215 Clayton St, 94117)
- **Domestic Destination**: Washington, DC (1600 Pennsylvania Ave NW, 20500)
- **International Destination**: London, UK (10 Downing Street, SW1A 2AA)
- **Parcel**: 10x8x4 in, 2 lb

## Extras Tested

This suite tests **42 distinct extras** across the following categories:

### Signature Confirmation
- `STANDARD`, `ADULT`, `CERTIFIED` (USPS), `INDIRECT` (FedEx), `CARRIER_CONFIRMATION` (Deutsche Post)

### Insurance
- Shippo/XCover third-party insurance
- Carrier-provided: FedEx, UPS, OnTrac

### COD (Collect on Delivery)
- `ANY`, `CASH`, `SECURED_FUNDS`

### Billing
- `RECIPIENT`, `THIRD_PARTY`, `COLLECT`

### Alcohol & Hazmat
- Alcohol (consumer/licensee), Dry Ice, Dangerous Goods, Lithium Batteries, Biological Material

### Delivery Options
- `saturday_delivery`, `authority_to_leave`, `delivery_instructions`, `carbon_neutral`, `premium`

### Reference Fields
- `reference_1/2`, `customer_reference`, `po_number`, `invoice_number`, `dept_number`, `rma_number`

### Return Options
- `is_return`, `return_service_type`

See `INSTRUCTIONS.md` for the complete extras reference.

## Output Files

| Module | Output Files |
|--------|--------------|
| `shippo_extras.py` | `*_raw.json`, `*_report.json`, `*_report.md` |
| `comparative_runner.py` | `*.json`, `*_matrix.json`, `*.md` |
| `service_level_analyzer.py` | `*_results.json`, `*_matrices.json`, `*_report.md` |

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

### Rate limiting

```bash
# Reduce concurrency
uv run python src/shippo_extras.py -j 2

# Or reduce test scope
uv run python src/shippo_extras.py --max-tests 20
```

## Requirements

- Python 3.11+
- `httpx>=0.25.0` - Async HTTP client
- `pytest>=7.0.0` - Test framework (dev)
- `pytest-asyncio>=0.21.0` - Async test support (dev)
- `ruff>=0.1.0` - Linting and formatting (dev)

## License

This test suite is provided as-is for integration development purposes.
