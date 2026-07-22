#!/usr/bin/env python3
"""Preflight common Shopify product CSV mistakes without external dependencies."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


VERSION = "0.1.0"

COLUMN_ALIASES = {
    "handle": ("URL handle", "Handle"),
    "title": ("Title",),
    "tags": ("Tags",),
    "published": ("Published on online store", "Published"),
    "status": ("Status",),
    "sku": ("SKU", "Variant SKU"),
    "barcode": ("Barcode", "Variant Barcode"),
    "option1_name": ("Option1 name", "Option1 Name"),
    "option1_value": ("Option1 value", "Option1 Value"),
    "option2_name": ("Option2 name", "Option2 Name"),
    "option2_value": ("Option2 value", "Option2 Value"),
    "option3_name": ("Option3 name", "Option3 Name"),
    "option3_value": ("Option3 value", "Option3 Value"),
    "price": ("Price", "Variant Price"),
    "compare_at_price": (
        "Compare-at price",
        "Variant Compare At Price",
        "Variant Compare-at Price",
    ),
    "cost": ("Cost per item",),
    "charge_tax": ("Charge tax", "Variant Taxable"),
    "inventory_tracker": ("Inventory tracker", "Variant Inventory Tracker"),
    "inventory_qty": ("Inventory quantity", "Variant Inventory Qty"),
    "inventory_policy": (
        "Continue selling when out of stock",
        "Variant Inventory Policy",
    ),
    "weight": ("Weight value (grams)", "Variant Grams"),
    "weight_unit": ("Weight unit for display", "Variant Weight Unit"),
    "requires_shipping": ("Requires shipping", "Variant Requires Shipping"),
    "fulfillment": ("Fulfillment service", "Variant Fulfillment Service"),
    "image_url": ("Product image URL", "Image Src"),
    "image_position": ("Image position", "Image Position"),
    "image_alt": ("Image alt text", "Image Alt Text"),
    "variant_image_url": ("Variant image URL", "Variant Image"),
    "gift_card": ("Gift card", "Gift Card"),
    "seo_title": ("SEO title", "SEO Title"),
    "seo_description": ("SEO description", "SEO Description"),
    "collection": ("Collection",),
}

VARIANT_FIELDS = {
    "sku",
    "barcode",
    "price",
    "compare_at_price",
    "cost",
    "charge_tax",
    "inventory_tracker",
    "inventory_qty",
    "inventory_policy",
    "weight",
    "weight_unit",
    "requires_shipping",
    "fulfillment",
    "variant_image_url",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    row: int = 0
    field: str = ""


class InputError(Exception):
    pass


def normalized_header(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def read_product_csv(path: Path) -> tuple[list[str], list[tuple[int, dict[str, str]]], list[Finding]]:
    findings: list[Finding] = []
    try:
        source = path.open("r", encoding="utf-8-sig", newline="")
    except (OSError, UnicodeError) as exc:
        raise InputError(f"Cannot open UTF-8 CSV: {exc}") from exc

    try:
        reader = csv.reader(source, strict=True)
        try:
            raw_headers = next(reader)
        except StopIteration as exc:
            raise InputError("CSV is empty") from exc

        if len(raw_headers) == 1 and ";" in raw_headers[0]:
            findings.append(
                Finding(
                    "error",
                    "csv.delimiter",
                    "The file appears to use semicolons; Shopify product CSV files require commas.",
                )
            )

        headers = [header.strip() for header in raw_headers]
        for raw, clean in zip(raw_headers, headers):
            if raw != clean:
                findings.append(
                    Finding(
                        "warning",
                        "header.whitespace",
                        f"Header has leading or trailing whitespace: {raw!r}.",
                        field=clean,
                    )
                )

        seen: dict[str, str] = {}
        for header in headers:
            key = normalized_header(header)
            if not key:
                findings.append(Finding("error", "header.blank", "A column header is blank."))
            elif key in seen:
                findings.append(
                    Finding(
                        "error",
                        "header.duplicate",
                        f"Duplicate column headers: {seen[key]!r} and {header!r}.",
                        field=header,
                    )
                )
            else:
                seen[key] = header

        rows: list[tuple[int, dict[str, str]]] = []
        for values in reader:
            line = reader.line_num
            if not any(value.strip() for value in values):
                continue
            if len(values) != len(headers):
                findings.append(
                    Finding(
                        "error",
                        "row.width",
                        f"Expected {len(headers)} cells but found {len(values)}.",
                        row=line,
                    )
                )
            padded = values[: len(headers)] + [""] * max(0, len(headers) - len(values))
            rows.append((line, dict(zip(headers, padded))))
        return headers, rows, findings
    except UnicodeError as exc:
        raise InputError(f"CSV is not valid UTF-8 near line {reader.line_num}: {exc}") from exc
    except csv.Error as exc:
        raise InputError(f"Malformed CSV near line {reader.line_num}: {exc}") from exc
    finally:
        source.close()


def bind_columns(headers: list[str]) -> tuple[dict[str, str], list[Finding]]:
    by_normalized: dict[str, list[str]] = defaultdict(list)
    for header in headers:
        by_normalized[normalized_header(header)].append(header)

    bound: dict[str, str] = {}
    findings: list[Finding] = []
    for semantic, aliases in COLUMN_ALIASES.items():
        matches: list[str] = []
        for alias in aliases:
            matches.extend(by_normalized.get(normalized_header(alias), []))
        matches = list(dict.fromkeys(matches))
        if matches:
            bound[semantic] = matches[0]
        if len(matches) > 1:
            findings.append(
                Finding(
                    "error",
                    "header.alias_conflict",
                    f"These columns mean the same thing: {', '.join(matches)}. Keep only one.",
                    field=matches[0],
                )
            )
    return bound, findings


def raw_value(row: dict[str, str], bound: dict[str, str], semantic: str) -> str:
    header = bound.get(semantic)
    return (row.get(header, "") if header else "") or ""


def value(row: dict[str, str], bound: dict[str, str], semantic: str) -> str:
    return raw_value(row, bound, semantic).strip()


def decimal_value(text: str) -> Decimal | None:
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def image_url_finding(text: str, row: int, field: str) -> Finding | None:
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return Finding("error", "image.url", "Image URL must be an absolute http(s) URL.", row, field)
    if parsed.scheme == "http":
        return Finding("warning", "image.http", "Use a public HTTPS image URL.", row, field)
    return None


def validate_product_csv(
    path: Path, mode: str = "create", require_sku: bool = False
) -> dict[str, object]:
    headers, rows, findings = read_product_csv(path)
    bound, binding_findings = bind_columns(headers)
    findings.extend(binding_findings)

    if "title" not in bound:
        findings.append(Finding("error", "header.title_missing", "Required Title column is missing."))
    if not rows:
        findings.append(Finding("error", "row.none", "CSV has a header but no product rows."))
    if mode == "update" and "handle" not in bound:
        findings.append(
            Finding("error", "header.handle_missing", "Update mode requires URL handle (or legacy Handle).")
        )

    present_variant_fields = VARIANT_FIELDS.intersection(bound)
    variant_option_headers_missing = bool(present_variant_fields) and not {
        "option1_name",
        "option1_value",
    }.issubset(bound)
    if mode == "update" and variant_option_headers_missing:
        findings.append(
            Finding(
                "error",
                "header.variant_options_missing",
                "Updating variant-related columns requires both Option1 name and Option1 value columns.",
            )
        )

    for index in range(1, 4):
        name_key, value_key = f"option{index}_name", f"option{index}_value"
        if (name_key in bound) != (value_key in bound):
            findings.append(
                Finding(
                    "error",
                    "header.option_pair",
                    f"Option{index} name and Option{index} value must be included together.",
                )
            )

    groups: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for line, row in rows:
        handle = value(row, bound, "handle")
        title = value(row, bound, "title")
        if handle:
            group_key = f"handle:{handle}"
        elif title:
            group_key = f"row:{line}"
            if mode == "update":
                findings.append(
                    Finding("error", "product.handle_missing", "Update row has no URL handle.", line, bound.get("handle", "URL handle"))
                )
        else:
            findings.append(
                Finding(
                    "error",
                    "row.unassociated",
                    "Row has data but no URL handle or Title, so Shopify cannot associate it with a product.",
                    line,
                )
            )
            continue
        groups.setdefault(group_key, []).append((line, row))

        if handle and (not handle.replace("-", "").isalnum() or " " in handle):
            findings.append(
                Finding(
                    "error",
                    "handle.invalid",
                    "URL handle may contain only letters, numbers, and dashes, with no spaces.",
                    line,
                    bound.get("handle", "URL handle"),
                )
            )

    if mode == "create" and variant_option_headers_missing:
        has_multirow_variant = any(
            sum(
                any(value(row, bound, key) for key in VARIANT_FIELDS)
                for _, row in group_rows
            )
            > 1
            for group_rows in groups.values()
        )
        if has_multirow_variant:
            findings.append(
                Finding(
                    "error",
                    "header.variant_options_missing",
                    "A multi-row variant product requires Option1 name and Option1 value columns.",
                )
            )

    exact_skus: dict[str, int] = {}
    normalized_skus: dict[str, tuple[str, int]] = {}

    boolean_keys = ("published", "charge_tax", "requires_shipping", "gift_card")
    decimal_keys = ("price", "compare_at_price", "cost")
    integer_pattern = re.compile(r"^[+-]?\d+$")
    unsigned_integer_pattern = re.compile(r"^[0-9]+$")

    market_prices: dict[str, str] = {}
    market_compares: dict[str, str] = {}
    market_included: dict[str, str] = {}
    for header in headers:
        normalized = normalized_header(header)
        if normalized.startswith("price / "):
            market_prices[normalized.removeprefix("price / ")] = header
        elif normalized.startswith("compare-at price / "):
            market_compares[normalized.removeprefix("compare-at price / ")] = header
        elif normalized.startswith("included / "):
            market_included[normalized.removeprefix("included / ")] = header

    for line, row in rows:
        for key in boolean_keys:
            text = value(row, bound, key)
            if text and text.casefold() not in {"true", "false"}:
                findings.append(
                    Finding("error", "value.boolean", "Value must be true or false.", line, bound[key])
                )

        if mode == "create" and value(row, bound, "gift_card").casefold() == "true":
            findings.append(
                Finding(
                    "error",
                    "gift_card.create",
                    "Shopify product CSV files can update gift cards but cannot create them.",
                    line,
                    bound["gift_card"],
                )
            )

        status = value(row, bound, "status")
        if status and status.casefold() not in {"active", "draft", "archived"}:
            findings.append(
                Finding("error", "status.invalid", "Status must be active, draft, or archived.", line, bound["status"])
            )

        policy = value(row, bound, "inventory_policy")
        if policy and policy.casefold() not in {"deny", "continue"}:
            findings.append(
                Finding("error", "inventory.policy", "Value must be deny or continue.", line, bound["inventory_policy"])
            )

        unit = value(row, bound, "weight_unit")
        if unit and unit.casefold() not in {"g", "kg", "lb", "oz"}:
            findings.append(
                Finding("error", "weight.unit", "Weight unit must be g, kg, lb, or oz.", line, bound["weight_unit"])
            )

        parsed_numbers: dict[str, Decimal] = {}
        for key in decimal_keys:
            text = value(row, bound, key)
            if not text:
                continue
            number = decimal_value(text)
            if number is None or number < 0:
                findings.append(
                    Finding("error", "money.invalid", "Use a non-negative number without a currency symbol.", line, bound[key])
                )
            else:
                parsed_numbers[key] = number
        if {"price", "compare_at_price"}.issubset(parsed_numbers) and parsed_numbers["compare_at_price"] <= parsed_numbers["price"]:
            findings.append(
                Finding(
                    "warning",
                    "price.compare_at",
                    "Compare-at price should be greater than Price to show a discount.",
                    line,
                    bound["compare_at_price"],
                )
            )

        weight = value(row, bound, "weight")
        if weight and not unsigned_integer_pattern.fullmatch(weight):
            findings.append(
                Finding("error", "weight.invalid", "Weight in grams must be a non-negative whole number.", line, bound["weight"])
            )

        quantity = value(row, bound, "inventory_qty")
        if quantity and not integer_pattern.fullmatch(quantity):
            findings.append(
                Finding("error", "inventory.quantity", "Inventory quantity must be a whole number.", line, bound["inventory_qty"])
            )

        position = value(row, bound, "image_position")
        if position and (
            not unsigned_integer_pattern.fullmatch(position) or int(position) < 1
        ):
            findings.append(
                Finding("error", "image.position", "Image position must be a whole number starting at 1.", line, bound["image_position"])
            )

        for key in ("image_url", "variant_image_url"):
            text = value(row, bound, key)
            if text:
                problem = image_url_finding(text, line, bound[key])
                if problem:
                    findings.append(problem)

        image_url = value(row, bound, "image_url")
        alt = value(row, bound, "image_alt")
        if image_url and not alt:
            findings.append(
                Finding(
                    "warning",
                    "image.alt_missing",
                    "Image has no alt text.",
                    line,
                    bound.get("image_alt", "Image alt text"),
                )
            )
        if len(alt) > 512:
            findings.append(
                Finding("error", "image.alt_length", "Image alt text exceeds Shopify's 512-character limit.", line, bound["image_alt"])
            )
        elif len(alt) > 125:
            findings.append(
                Finding("warning", "image.alt_long", "Image alt text is longer than the recommended 125 characters.", line, bound["image_alt"])
            )

        seo_title = value(row, bound, "seo_title")
        if len(seo_title) > 70:
            findings.append(
                Finding("error", "seo.title_length", "SEO title exceeds Shopify's 70-character limit.", line, bound["seo_title"])
            )
        seo_description = value(row, bound, "seo_description")
        if len(seo_description) > 320:
            findings.append(
                Finding("error", "seo.description_length", "SEO description exceeds Shopify's 320-character limit.", line, bound["seo_description"])
            )

        tags = value(row, bound, "tags")
        if tags and len([tag for tag in tags.split(",") if tag.strip()]) > 250:
            findings.append(
                Finding("error", "tags.count", "A product can have at most 250 tags.", line, bound["tags"])
            )

        collection = value(row, bound, "collection")
        if len(collection) > 255:
            findings.append(
                Finding("error", "collection.length", "Collection name exceeds 255 characters.", line, bound["collection"])
            )

        market_price_values: dict[str, Decimal] = {}
        for market, price_header in market_prices.items():
            price_text = (row.get(price_header) or "").strip()
            if not price_text:
                continue
            price_number = decimal_value(price_text)
            if price_number is None or price_number < 0:
                findings.append(
                    Finding(
                        "error",
                        "money.invalid",
                        "Use a non-negative number without a currency symbol.",
                        line,
                        price_header,
                    )
                )
            else:
                market_price_values[market] = price_number

        for included_header in market_included.values():
            included = (row.get(included_header) or "").strip()
            if included and included.casefold() not in {"true", "false"}:
                findings.append(
                    Finding(
                        "error",
                        "value.boolean",
                        "Value must be true or false.",
                        line,
                        included_header,
                    )
                )

        for market, compare_header in market_compares.items():
            compare_text = (row.get(compare_header) or "").strip()
            if not compare_text:
                continue
            compare_number = decimal_value(compare_text)
            if compare_number is None or compare_number < 0:
                findings.append(
                    Finding("error", "money.invalid", "Use a non-negative number without a currency symbol.", line, compare_header)
                )
            price_header = market_prices.get(market)
            price_text = (row.get(price_header) or "").strip() if price_header else ""
            price_number = market_price_values.get(market)
            if not price_header or not price_text or price_number is None:
                findings.append(
                    Finding(
                        "error",
                        "market.price_missing",
                        "A market compare-at price requires the matching market Price value.",
                        line,
                        compare_header,
                    )
                )
            elif compare_number is not None and compare_number <= price_number:
                findings.append(
                    Finding(
                        "warning",
                        "price.compare_at",
                        "Market compare-at price should be greater than the matching market Price.",
                        line,
                        compare_header,
                    )
                )

        sku_raw = raw_value(row, bound, "sku")
        sku = sku_raw.strip()
        if sku:
            if sku_raw != sku:
                findings.append(
                    Finding("warning", "sku.whitespace", "SKU has leading or trailing whitespace.", line, bound["sku"])
                )
            if sku in exact_skus:
                findings.append(
                    Finding(
                        "warning",
                        "sku.duplicate",
                        f"Duplicate SKU {sku!r}; first seen on row {exact_skus[sku]}.",
                        line,
                        bound["sku"],
                    )
                )
            else:
                exact_skus[sku] = line
            normalized = sku.casefold()
            previous = normalized_skus.get(normalized)
            if previous and previous[0] != sku:
                findings.append(
                    Finding(
                        "warning",
                        "sku.case_collision",
                        f"SKU differs only by letter case from {previous[0]!r} on row {previous[1]}.",
                        line,
                        bound["sku"],
                    )
                )
            else:
                normalized_skus[normalized] = (sku, line)

        fulfillment = value(row, bound, "fulfillment")
        if fulfillment and fulfillment.casefold() != "manual" and not sku:
            findings.append(
                Finding(
                    "error",
                    "fulfillment.sku_missing",
                    "A custom fulfillment service requires a SKU.",
                    line,
                    bound.get("sku", "SKU"),
                )
            )

    for group_rows in groups.values():
        first_line, first_row = group_rows[0]
        if not value(first_row, bound, "title"):
            findings.append(
                Finding(
                    "error",
                    "product.title_missing",
                    "The first row for this product has no Title.",
                    first_line,
                    bound.get("title", "Title"),
                )
            )
        if "status" in bound and not value(first_row, bound, "status"):
            findings.append(
                Finding(
                    "error",
                    "status.missing",
                    "Status column is present but the product value is blank.",
                    first_line,
                    bound["status"],
                )
            )

        option_values_present: set[int] = set()
        for index in range(1, 4):
            names = {
                value(row, bound, f"option{index}_name")
                for _, row in group_rows
                if value(row, bound, f"option{index}_name")
            }
            values = [
                (line, value(row, bound, f"option{index}_value"))
                for line, row in group_rows
                if value(row, bound, f"option{index}_value")
            ]
            if len(names) > 1:
                findings.append(
                    Finding(
                        "error",
                        "option.name_conflict",
                        f"A product uses multiple Option{index} names: {', '.join(sorted(names))}.",
                        first_line,
                        bound.get(f"option{index}_name", f"Option{index} name"),
                    )
                )
            if values:
                option_values_present.add(index)
                if not names:
                    findings.append(
                        Finding(
                            "error",
                            "option.name_missing",
                            f"Option{index} has values but no name for this product.",
                            values[0][0],
                            bound.get(f"option{index}_name", f"Option{index} name"),
                        )
                    )

        if 3 in option_values_present and 2 not in option_values_present:
            findings.append(
                Finding("error", "option.gap", "Option3 is used without Option2.", first_line)
            )
        if 2 in option_values_present and 1 not in option_values_present:
            findings.append(
                Finding("error", "option.gap", "Option2 is used without Option1.", first_line)
            )

        variants: dict[tuple[str, str, str], int] = {}
        for line, row in group_rows:
            option_tuple = tuple(value(row, bound, f"option{index}_value") for index in range(1, 4))
            has_variant_data = any(value(row, bound, key) for key in VARIANT_FIELDS)
            image_only = bool(value(row, bound, "image_url")) and not has_variant_data and not any(option_tuple)
            is_variant_row = has_variant_data or any(option_tuple)
            if is_variant_row:
                for index in sorted(option_values_present):
                    if not option_tuple[index - 1]:
                        findings.append(
                            Finding(
                                "error",
                                "variant.option_missing",
                                f"Variant is missing Option{index} value used by this product.",
                                line,
                                bound.get(f"option{index}_value", f"Option{index} value"),
                            )
                        )
            if any(option_tuple):
                if option_tuple in variants:
                    findings.append(
                        Finding(
                            "error",
                            "variant.duplicate",
                            f"Duplicate option combination; first seen on row {variants[option_tuple]}.",
                            line,
                            bound.get("option1_value", "Option1 value"),
                        )
                    )
                else:
                    variants[option_tuple] = line
            if require_sku and not image_only and (is_variant_row or line == first_line) and not value(row, bound, "sku"):
                findings.append(
                    Finding(
                        "error",
                        "sku.missing",
                        "SKU is required by --require-sku.",
                        line,
                        bound.get("sku", "SKU"),
                    )
                )

        if not value(first_row, bound, "handle") and any(option_values_present):
            first_option = value(first_row, bound, "option1_value").casefold()
            if len(group_rows) > 1 or first_option not in {"", "default title"}:
                findings.append(
                    Finding(
                        "error",
                        "variant.handle_missing",
                        "Products with variants need a URL handle.",
                        first_line,
                        bound.get("handle", "URL handle"),
                    )
                )

    severity_order = {"error": 0, "warning": 1}
    findings.sort(key=lambda item: (item.row, severity_order[item.severity], item.code, item.field))
    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    return {
        "tool_version": VERSION,
        "file": str(path),
        "mode": mode,
        "row_count": len(rows),
        "summary": {"errors": errors, "warnings": warnings},
        "findings": [asdict(item) for item in findings],
    }


def print_report(report: dict[str, object]) -> None:
    summary = report["summary"]
    assert isinstance(summary, dict)
    print(f"Shopify Catalog Doctor {report['tool_version']}")
    print(f"File: {report['file']}")
    print(f"Rows: {report['row_count']} | Errors: {summary['errors']} | Warnings: {summary['warnings']}")
    findings = report["findings"]
    assert isinstance(findings, list)
    if not findings:
        print("PASS: no common import problems found.")
        return
    for item in findings:
        assert isinstance(item, dict)
        location = f"row {item['row']}" if item["row"] else "file"
        field = f" | {item['field']}" if item["field"] else ""
        print(f"[{str(item['severity']).upper()}] {location}{field} | {item['code']}: {item['message']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find common Shopify product CSV problems before import."
    )
    parser.add_argument("csv_file", type=Path, help="Shopify product CSV file")
    parser.add_argument(
        "--mode",
        choices=("create", "update"),
        default="create",
        help="Use update to require URL handles (default: create)",
    )
    parser.add_argument("--require-sku", action="store_true", help="Treat missing variant SKUs as errors")
    parser.add_argument("--json", type=Path, metavar="REPORT.json", help="Write a machine-readable report")
    parser.add_argument("--warnings-as-errors", action="store_true", help="Return exit code 1 for warnings")
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.json and args.csv_file.resolve() == args.json.resolve():
        print("ERROR: JSON report path must not overwrite the input CSV.", file=sys.stderr)
        return 2
    try:
        report = validate_product_csv(args.csv_file, args.mode, args.require_sku)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print_report(report)
    if args.json:
        try:
            args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot write JSON report: {exc}", file=sys.stderr)
            return 2

    summary = report["summary"]
    assert isinstance(summary, dict)
    if summary["errors"] or (args.warnings_as_errors and summary["warnings"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
