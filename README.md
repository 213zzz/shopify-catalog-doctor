# Shopify Catalog Doctor

A zero-dependency command-line preflight checker for Shopify product CSV files.
It catches common catalog mistakes before an import changes store data.

> Unofficial community tool. Not affiliated with or endorsed by Shopify.

## What it checks

- Missing or conflicting Shopify columns
- Invalid URL handles and unassociated rows
- Duplicate SKUs and case-only SKU collisions
- Duplicate or incomplete variant option combinations
- Invalid prices, compare-at prices, weights, inventory values, and booleans
- Broken image URL formats and missing or oversized alt text
- SEO title, SEO description, tag, and collection length limits
- Current Shopify column names and common legacy export names

The rules follow Shopify's current [product CSV documentation](https://help.shopify.com/en/manual/products/import-export/using-csv). Shopify remains the final authority and can apply additional store-specific validation.

## Quick start

Requires Python 3.9 or newer. No packages to install.

```bash
python shopify_catalog_doctor.py products.csv
```

For an update CSV, require product handles:

```bash
python shopify_catalog_doctor.py products.csv --mode update
```

Require every product or variant row to have a SKU:

```bash
python shopify_catalog_doctor.py products.csv --require-sku
```

Create a JSON report for automation:

```bash
python shopify_catalog_doctor.py products.csv --json report.json
```

Exit codes:

- `0`: no errors
- `1`: validation errors, or warnings with `--warnings-as-errors`
- `2`: the CSV or JSON report could not be read or written

## 中文说明

这是一个完全本地运行的 Shopify 商品 CSV 导入前检查工具。它不会连接店铺，也不需要 Admin API Token。

在 Windows PowerShell 中运行：

```powershell
python .\shopify_catalog_doctor.py .\products.csv
```

如果你正在批量更新已有商品，使用：

```powershell
python .\shopify_catalog_doctor.py .\products.csv --mode update --require-sku
```

## Test

```bash
python -m unittest -v
```

## License

[MIT](LICENSE)
