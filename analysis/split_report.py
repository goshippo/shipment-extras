#!/usr/bin/env python3
"""
Split the shippo_extras_results_report.md into individual carrier files
and generate swagger update prompts for each carrier.
"""

import os
import re
from collections import defaultdict
from pathlib import Path

REPORT_PATH = "shippo_extras_results_report.md"
OUTPUT_DIR = "carrier_reports"
PROMPTS_DIR = "swagger_update_prompts"


def parse_report(report_path: str) -> dict[str, list[tuple[str, str]]]:
    """
    Parse the report and group service levels by carrier.

    Returns:
        Dict mapping carrier name to list of (service_level, content) tuples
    """
    with open(report_path, "r") as f:
        content = f.read()

    # Split by ### headers
    sections = re.split(r'^(### .+)$', content, flags=re.MULTILINE)

    carriers: dict[str, list[tuple[str, str]]] = defaultdict(list)

    i = 1  # Start after the intro section
    while i < len(sections):
        header = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""

        # Parse carrier - service_level format
        match = re.match(r'^### ([a-z_]+) - (.+)$', header)
        if match:
            carrier = match.group(1)
            service_level = match.group(2)
            carriers[carrier].append((service_level, header + "\n" + body))

        i += 2

    return dict(carriers)


def extract_header_section(report_path: str) -> str:
    """Extract the header/summary section before carrier details."""
    with open(report_path, "r") as f:
        content = f.read()

    # Find the first ### carrier - service pattern
    match = re.search(r'^### [a-z_]+ - ', content, flags=re.MULTILINE)
    if match:
        return content[:match.start()]
    return ""


def analyze_extras(service_levels: list[tuple[str, str]]) -> dict:
    """
    Analyze extras across all service levels for a carrier.
    
    Returns dict with:
        - all_supported: set of extras supported by at least one service level
        - all_not_supported: set of extras not supported by any service level
        - universal_extras: set of extras supported by ALL service levels
        - never_supported: set of extras not supported by ANY service level
        - service_support_map: dict mapping service level to supported/not_supported sets
    """
    all_supported: set[str] = set()
    all_not_supported: set[str] = set()
    service_support_map: dict[str, dict[str, set[str]]] = {}
    
    for service_level, content in service_levels:
        supported: set[str] = set()
        not_supported: set[str] = set()
        
        in_supported = False
        in_not_supported = False
        
        for line in content.split('\n'):
            line_stripped = line.strip()
            if '**Supported' in line and 'Not' not in line:
                in_supported = True
                in_not_supported = False
            elif '**Not Supported' in line:
                in_supported = False
                in_not_supported = True
            elif line.startswith('### '):
                in_supported = False
                in_not_supported = False
            elif in_supported and '✓' in line:
                extra = line_stripped.replace('- ✓', '').replace('✓', '').strip()
                if extra:
                    supported.add(extra)
                    all_supported.add(extra)
            elif in_not_supported and '✗' in line:
                extra = line_stripped.replace('- ✗', '').replace('✗', '').strip()
                if extra:
                    not_supported.add(extra)
                    all_not_supported.add(extra)
        
        service_support_map[service_level] = {
            'supported': supported,
            'not_supported': not_supported
        }
    
    # Calculate universal extras (supported by ALL service levels)
    universal_extras: set[str] = set()
    if service_levels:
        first_sl = service_levels[0][0]
        universal_extras = service_support_map[first_sl]['supported'].copy()
        for sl, _ in service_levels[1:]:
            universal_extras &= service_support_map[sl]['supported']
    
    # Calculate never supported (not supported by ANY service level)
    never_supported = all_not_supported - all_supported
    
    return {
        'all_supported': all_supported,
        'all_not_supported': all_not_supported,
        'universal_extras': universal_extras,
        'never_supported': never_supported,
        'service_support_map': service_support_map,
    }


def write_carrier_report(
    output_dir: str,
    carrier: str,
    service_levels: list[tuple[str, str]],
    header: str
) -> str:
    """Write a carrier-specific report and return the file path."""
    os.makedirs(output_dir, exist_ok=True)

    filepath = os.path.join(output_dir, f"{carrier}_report.md")
    
    # Analyze extras for this carrier
    analysis = analyze_extras(service_levels)

    with open(filepath, "w") as f:
        f.write(f"# {carrier.replace('_', ' ').title()} Extras Capability Report\n\n")
        f.write(f"Total Service Levels: {len(service_levels)}\n\n")
        
        # Summary section
        f.write("## Summary\n\n")
        
        # Universal extras (supported by ALL service levels)
        f.write(f"### Universal Extras (Supported by ALL {len(service_levels)} service levels)\n\n")
        if analysis['universal_extras']:
            for extra in sorted(analysis['universal_extras']):
                f.write(f"- ✓ {extra}\n")
        else:
            f.write("*No extras are supported across all service levels*\n")
        f.write("\n")
        
        # Extras supported by at least one service level
        partial_support = analysis['all_supported'] - analysis['universal_extras']
        if partial_support:
            f.write("### Partial Support (Supported by some but not all service levels)\n\n")
            for extra in sorted(partial_support):
                f.write(f"- ~ {extra}\n")
            f.write("\n")
        
        # Never supported extras
        f.write("### Never Supported (Not supported by any service level)\n\n")
        if analysis['never_supported']:
            for extra in sorted(analysis['never_supported']):
                f.write(f"- ✗ {extra}\n")
        else:
            f.write("*All tested extras are supported by at least one service level*\n")
        f.write("\n")
        
        # Detailed service level support
        f.write("---\n\n")
        f.write("## Service Level Support Details\n\n")

        for service_level, content in service_levels:
            f.write(content)
            if not content.endswith("\n\n"):
                f.write("\n")

    return filepath


def generate_swagger_prompt(carrier: str, service_levels: list[tuple[str, str]]) -> str:
    """Generate a prompt for updating swagger.yaml for a specific carrier."""

    # Use the analyze_extras function
    analysis = analyze_extras(service_levels)
    
    all_supported = analysis['all_supported']
    universal_extras = analysis['universal_extras']
    never_supported = analysis['never_supported']
    service_support_map = analysis['service_support_map']
    partial_support = all_supported - universal_extras

    # Build the prompt
    prompt = f"""# Swagger Update Prompt for {carrier.replace('_', ' ').title()}

## Overview
Update the swagger.yaml to accurately reflect the shipment extras supported by {carrier} carrier service levels.

## Carrier: {carrier}

## Service Levels Tested ({len(service_levels)} total)
{chr(10).join(f'- {sl}' for sl, _ in service_levels)}

## Summary of Extras Support

### Universal Extras (Supported by ALL {len(service_levels)} service levels)
{chr(10).join(f'- ✓ {e}' for e in sorted(universal_extras)) if universal_extras else '- None'}

### Partial Support (Supported by some but not all service levels)
{chr(10).join(f'- ~ {e}' for e in sorted(partial_support)) if partial_support else '- None'}

### Never Supported (Not supported by any service level)
{chr(10).join(f'- ✗ {e}' for e in sorted(never_supported)) if never_supported else '- None'}

## Detailed Service Level Support

"""

    for service_level, support in service_support_map.items():
        prompt += f"### {service_level}\n\n"

        if support['supported']:
            prompt += "**Supported Extras:**\n"
            for extra in sorted(support['supported']):
                prompt += f"- {extra}\n"
            prompt += "\n"

        if support['not_supported']:
            prompt += "**Not Supported Extras:**\n"
            for extra in sorted(support['not_supported']):
                prompt += f"- {extra}\n"
            prompt += "\n"

    prompt += """
## Instructions for Swagger Update

1. Locate the service level definitions in swagger.yaml for this carrier
2. For each service level, update the `extras` or `supported_extras` field to match the supported extras list above
3. Ensure the swagger documentation accurately reflects:
   - Which extras are available for each service level
   - Any carrier-specific extra configurations (e.g., signature types, insurance providers)
   - Proper enum values and descriptions for each extra type

## Extra Type Mappings

The test extras map to swagger fields as follows:
- `alcohol_consumer` / `alcohol_licensee` → `extra.alcohol.recipient_type`
- `ancillary_endorsement_*` → `extra.ancillary_endorsement`
- `authority_to_leave` → `extra.authority_to_leave`
- `billing_*` → `extra.billing.type`
- `bypass_address_validation` → `extra.bypass_address_validation`
- `carbon_neutral` → `extra.carbon_neutral`
- `cod_*` → `extra.COD.payment_method`
- `customer_reference` → `extra.customer_reference`
- `dangerous_goods*` → `extra.dangerous_goods`
- `delivery_instructions` → `extra.delivery_instructions`
- `dept_number` → `extra.dept_number`
- `dry_ice` → `extra.dry_ice`
- `insurance_*` → `extra.insurance.provider`
- `invoice_number` → `extra.invoice_number`
- `is_return` → `extra.is_return`
- `po_number` → `extra.po_number`
- `premium` → `extra.premium`
- `qr_code_requested` → `extra.qr_code_requested`
- `reference_1` / `reference_2` → `extra.reference_1` / `extra.reference_2`
- `return_service_*` → `extra.return_service_type`
- `rma_number` → `extra.rma_number`
- `saturday_delivery` → `extra.saturday_delivery`
- `signature_confirmation*` → `extra.signature_confirmation`

"""

    return prompt


def main():
    print("Parsing report...")
    carriers = parse_report(REPORT_PATH)
    header = extract_header_section(REPORT_PATH)

    print(f"Found {len(carriers)} carriers:")
    for carrier, service_levels in sorted(carriers.items()):
        print(f"  - {carrier}: {len(service_levels)} service levels")

    # Create carrier reports
    print(f"\nWriting carrier reports to {OUTPUT_DIR}/...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for carrier, service_levels in sorted(carriers.items()):
        filepath = write_carrier_report(OUTPUT_DIR, carrier, service_levels, header)
        print(f"  Created: {filepath}")

    # Generate swagger update prompts
    print(f"\nGenerating swagger update prompts to {PROMPTS_DIR}/...")
    os.makedirs(PROMPTS_DIR, exist_ok=True)

    for carrier, service_levels in sorted(carriers.items()):
        prompt = generate_swagger_prompt(carrier, service_levels)
        filepath = os.path.join(PROMPTS_DIR, f"{carrier}_swagger_prompt.md")
        with open(filepath, "w") as f:
            f.write(prompt)
        print(f"  Created: {filepath}")

    print("\nDone!")


if __name__ == "__main__":
    main()
