# Shippo Extras Discovery Suite

Empirical testing suite to discover which shipment extras are supported by each carrier and service level in the Shippo API.

## Background

This project originated from a technical discovery call with **Ordoro**, a Shippo partner, to determine which shipment extras should be available for each carrier and service level. During integration discussions, it became clear that the existing API documentation and MCP schema lacked comprehensive carrier-to-extras mappings, making it difficult for partners to build accurate shipping UIs and construct valid API requests.

This suite was built to empirically test every carrier/service/extra combination and produce actionable documentation that can be used to:
- Inform partner integrations (like Ordoro's)
- Update the Shippo API swagger specification
- Improve developer experience with accurate capability matrices

## Why This Exists

The Shippo API documentation and MCP schema don't provide a complete carrier-to-extras mapping. Different carriers support different shipment extras (signature confirmation, insurance, COD, etc.), and this support varies by service level within the same carrier.

This suite tests each combination empirically and builds a comprehensive capability matrix, enabling:
- **Accurate feature toggles** in shipping UIs
- **Valid API request construction** per carrier/service
- **Documentation updates** for the Shippo swagger spec

## How We Tested

### Evaluation Methodology

Each shipment extra is evaluated through a multi-stage testing process designed to determine not just whether an extra is accepted, but whether it actually affects the shipment.

#### Stage 1: Discovery Testing

**File**: `tests/test_shippo_extras.py`

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

**Output Files**:
| File | Description |
|------|-------------|
| `analysis/shippo_extras_results_raw.json` | Complete test execution data for every carrier/service/extra combination |
| `analysis/shippo_extras_results_report.json` | Aggregated support matrix by carrier |
| `analysis/shippo_extras_results_report.md` | Human-readable summary with findings |

#### Stage 2: Comparative Testing

**File**: `tests/comparative_test.py`

The key innovation—creates a **baseline shipment without extras**, then compares it to shipments **with** each extra to detect actual support vs. silent ignoring:

```
┌─────────────────────┐                    ┌─────────────────────┐
│ Baseline Shipment   │                    │ Shipment + Extra    │
│ (no extras)         │                    │                     │
└─────────┬───────────┘                    └─────────┬───────────┘
          │                                          │
          ▼                                          ▼
┌─────────────────────┐                    ┌─────────────────────┐
│ Baseline Response   │◀───── COMPARE ─────▶│ Extra Response      │
│ - rates             │                    │ - rates             │
│ - messages          │                    │ - messages          │
│ - available svcs    │                    │ - available svcs    │
└─────────────────────┘                    └─────────────────────┘
                                                     │
          ┌──────────────────────────────────────────┼──────────────────────────────────────────┐
          ▼                                          ▼                                          ▼
   ┌─────────────┐                           ┌─────────────┐                           ┌─────────────┐
   │ RATES SAME  │                           │RATES DIFFER │                           │ EXTRA FAILED│
   │ = IGNORED   │                           │= MODIFIED   │                           │ = REJECTED  │
   └─────────────┘                           └─────────────┘                           └─────────────┘
```

**Output Files**:
| File | Description |
|------|-------------|
| `*_comparative.json` | Detailed baseline vs. extra comparison results |
| `*_comparative_matrix.json` | Per-service-level support matrix |
| `*_comparative.md` | Markdown report with recommendations |

#### Stage 3: Service Level Analysis

**File**: `analysis/service_level_analyzer.py`

Categorizes service levels (express, ground, economy) and identifies patterns like "Saturday delivery only works with express services":

**Output Files**:
| File | Description |
|------|-------------|
| `*_service_results.json` | Results tagged with service tier categories |
| `*_service_matrices.json` | Cross-tier support comparison |
| `*_service_report.md` | Pattern analysis report |

#### Stage 4: Per-Carrier Report Generation

**File**: `analysis/split_report.py`

Splits the master report into individual carrier reports for focused review:

**Output Files**:
| File | Description |
|------|-------------|
| `analysis/carrier_reports/{carrier}_report.md` | Individual carrier analysis with service-level breakdown |

### Validation Types

Each test produces one of the following validation results:

| Result | What Happens | Confidence | Interpretation |
|--------|--------------|------------|----------------|
| `EXTRA_ACCEPTED` | API accepts request, returns rates | **High** | Extra is recognized by the carrier |
| `EXTRA_REJECTED` | API returns error mentioning the extra | **High** | Extra is explicitly not supported |
| `EXTRA_MODIFIED_RATES` | Rate amounts differ from baseline | **Very High** | Extra is actively applied (e.g., signature adds $2.50) |
| `EXTRA_IGNORED` | Response identical to baseline | **Low** | Extra may be unsupported, or supported but with no visible effect |
| `BASELINE_FAILED` | Baseline shipment couldn't be created | **N/A** | Service level not available for test route |
| `INVALID_VALUE` | Error indicates wrong value format | **Medium** | Extra exists but test value may be incorrect |

#### Understanding Confidence Levels

- **Very High (`EXTRA_MODIFIED_RATES`)**: The extra demonstrably changed something—this is definitive proof of support
- **High (`EXTRA_ACCEPTED`, `EXTRA_REJECTED`)**: Clear API signal about support or rejection
- **Low (`EXTRA_IGNORED`)**: Requires investigation—the extra might be:
  - Truly unsupported (carrier ignores unknown fields)
  - Supported but inactive (e.g., no rate impact for this route)
  - Requires specific conditions (e.g., alcohol extras need alcohol shipment content)

### Test Data

- **Origin**: San Francisco, CA (215 Clayton St, 94117)
- **Domestic Destination**: Washington, DC (1600 Pennsylvania Ave NW, 20500)
- **International Destination**: London, UK (10 Downing Street, SW1A 2AA)
- **Parcel**: 10x8x4 in, 2 lb

## Project Structure

```
shipment-extras/
├── README.md                    # This file
├── INSTRUCTIONS.md              # Detailed usage instructions
│
├── tests/                       # Test execution scripts
│   ├── test_shippo_extras.py    # Basic discovery tests
│   └── comparative_test.py      # Comparative analysis tests
│
├── analysis/                    # Results and analysis
│   ├── shippo_extras_results_raw.json      # Raw test results
│   ├── shippo_extras_results_report.json   # Aggregated report
│   ├── shippo_extras_results_report.md     # Human-readable summary
│   ├── service_level_analyzer.py           # Service-level pattern analyzer
│   ├── split_report.py                     # Report splitting utility
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
        ├── ups_swagger_prompt.md
        └── ...
```

## Results Structure

### Raw Results (`*_raw.json`)

Complete test execution data:
```json
{
  "carrier": "usps",
  "service_level": "usps_priority",
  "extra_name": "signature_confirmation",
  "extra_value": "STANDARD",
  "result": "ACCEPTED",
  "rates_returned": 3,
  "response_time_ms": 245,
  "full_response": { ... }
}
```

### Aggregated Report (`*_report.json`)

Summarized by carrier and extra:
```json
{
  "usps": {
    "signature_confirmation": {
      "supported_services": ["usps_priority", "usps_express"],
      "rejected_services": [],
      "unknown_services": ["usps_ground_advantage"]
    }
  }
}
```

### Carrier Reports (`analysis/carrier_reports/*.md`)

Human-readable analysis per carrier including:
- Supported extras with which service levels
- Rejected extras with error details
- Recommendations for swagger updates

### Swagger Update Prompts (`swagger/swagger_update_prompts/*.md`)

Ready-to-use prompts for updating the Shippo swagger spec with discovered carrier capabilities. Each prompt contains carrier-specific findings formatted for direct use in updating `swagger/swagger.yaml`.

## Result Categories

See [Validation Types](#validation-types) above for detailed explanation of each result category and confidence levels.

## Quick Start

```bash
# Set API key
export SHIPPO_API_KEY="shippo_test_xxxxx"

# List available carriers
python tests/test_shippo_extras.py --list-carriers

# Run a quick test
python tests/test_shippo_extras.py --carrier usps --max-tests 10

# Run full discovery
python tests/test_shippo_extras.py

# Run comparative analysis
python tests/comparative_test.py
```

See `INSTRUCTIONS.md` for detailed usage, troubleshooting, and extension guidance.

## Extras Tested

This suite tests **42 distinct extras** from the [Shippo Shipment Extras API](https://goshippo.com/docs/reference#shipments-extras) across the following categories:

### Signature Confirmation
- `STANDARD` - Standard signature confirmation
- `ADULT` - Adult signature required
- `CERTIFIED` - Certified mail (USPS)
- `INDIRECT` - Indirect signature (FedEx)
- `CARRIER_CONFIRMATION` - Carrier confirmation (Deutsche Post)

### Insurance
- **Shippo/XCover** - Third-party insurance via Shippo
- **FedEx** - Carrier-provided insurance (provider: FEDEX)
- **UPS** - Carrier-provided insurance (provider: UPS)
- **OnTrac** - Carrier-provided insurance (provider: ONTRAC)

### COD (Collect on Delivery)
- `ANY` - Any payment method accepted
- `CASH` - Cash only
- `SECURED_FUNDS` - Secured funds (money orders, certified checks)

### Billing
- `RECIPIENT` - Bill recipient for shipping
- `THIRD_PARTY` - Bill third party account
- `COLLECT` - Collect billing

### Alcohol & Hazmat
- **Alcohol** - consumer and licensee recipient types
- **Dry Ice** - Weight-specified dry ice shipments
- **Dangerous Goods** - General dangerous goods flag
- **Lithium Batteries** - Lithium battery contents
- **Biological Material** - Biological material contents
- **DG Code** - DHL eCommerce dangerous goods codes

### Delivery Options
- `saturday_delivery` - Saturday delivery service
- `authority_to_leave` - Leave without signature
- `delivery_instructions` - Custom delivery instructions
- `carbon_neutral` - Carbon neutral shipping
- `premium` - Premium service tier

### Reference Fields
- `reference_1` / `reference_2` - Generic reference fields
- `customer_reference` - Customer reference on label
- `po_number` - Purchase order number
- `invoice_number` - Invoice number
- `dept_number` - Department number
- `rma_number` - Return merchandise authorization

### Return Options
- `is_return` - Mark as return shipment
- `return_service_type` - PRINT_AND_MAIL, ELECTRONIC_LABEL

### Other Extras
- `qr_code_requested` - Request QR code for label
- `bypass_address_validation` - Skip address validation
- `ancillary_endorsement` - FORWARDING_SERVICE_REQUESTED, RETURN_SERVICE_REQUESTED (DHL eCommerce)
- `preferred_delivery_timeframe` - Delivery time window (DHL Germany)
- `lasership_declared_value` - Declared value (LaserShip)
- `lasership_attrs` - Special attributes: Alcohol, Perishable (LaserShip)

## Extras NOT Tested

The following extras exist in the [Shippo API schema](https://goshippo.com/docs/reference#shipments-extras) but were **not included** in this test suite (typically specialized reference/tracking fields with limited carrier support):

| Extra | Description |
|-------|-------------|
| `accounts_receivable_customer_account` | AR customer account reference |
| `appropriation_number` | Appropriation number reference |
| `bill_of_lading_number` | Bill of lading reference |
| `carrier_hub_id` | Carrier hub identifier |
| `carrier_hub_travel_time` | Hub travel time specification |
| `cod_number` | COD reference number |
| `container_type` | Container type specification |
| `critical_pull_time` | Critical pull time for fulfillment |
| `customer_branch` | Customer branch identifier |
| `dealer_order_number` | Dealer order reference |
| `fda_product_code` | FDA product code for regulated items |
| `fulfillment_center` | Fulfillment center identifier |
| `manifest_number` | Manifest reference number |
| `model_number` | Model number reference |
| `part_number` | Part number reference |
| `production_code` | Production code reference |
| `purchase_request_number` | Purchase request reference |
| `request_retail_rates` | Request retail rate pricing |
| `salesperson_number` | Salesperson reference |
| `serial_number` | Serial number reference |
| `store_number` | Store number reference |
| `transaction_reference_number` | Transaction reference |

> **Note**: These extras are primarily specialized reference fields used for internal tracking, B2B shipments, or carrier-specific workflows. They can be added to the test suite by extending `EXTRAS_TO_TEST` in `tests/test_shippo_extras.py`.

## Requirements

- Python 3.8+
- `requests` library
- Shippo API key with connected carrier accounts
