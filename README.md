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

### 这个工具有什么作用？

**Shopify Catalog Doctor 用于在商品 CSV 导入 Shopify 之前发现数据问题。**

错误的 CSV 可能导致 SKU 混乱、商品变体重复或被重建、促销价格失效、图片无法导入。这个工具会提前指出具体问题所在的行和字段，适合批量创建商品或更新已有商品前使用。

它主要检查：

- SKU 重复、缺失、前后空格和大小写冲突
- 颜色、尺寸等变体选项缺失、重复或组合不完整
- Price、Compare-at price、库存和重量格式错误
- Handle、Status、布尔值及 Shopify 必需字段错误
- 图片 URL、图片 Alt 文本和 SEO 字段问题
- CSV 编码、分隔符、引号和列数错误
- Shopify 当前字段名和常见旧版导出字段名

工具只读取 CSV 并输出检查报告：**不会修改原始 CSV，不会连接或修改 Shopify 店铺，也不需要 Admin API Token。**

### 使用方法

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
