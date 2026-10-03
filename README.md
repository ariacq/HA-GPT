# Practical Local Inventory App (Mac) — Streamlit + SQLite

This version is rebuilt as a **simple, practical local inventory app** for Mac. It mirrors your spreadsheet workflow:

- Scan barcode into a register-style field
- Blank barcode => do nothing
- Match barcode => auto-fill item details
- No match => clear **NOT FOUND** and immediate quick-add onboarding

The app is intentionally basic: scanner speed + reliability first, not visual polish.

## Quantity-before-scan workflow (new)

- In **Stock In**, **Stock Out**, and **New Sale**:
  1) Type quantity (1–3 digits) and press Enter (example: `5`)
  2) Scan barcode and scanner Enter submits
  3) App uses pending quantity, then resets back to default
- If you scan barcode directly, quantity defaults to `1`.
- Barcode detection uses a minimum length rule (default: `>= 7` chars).

## File structure

```text
HA-GPT/
├── app.py                     # Streamlit UI: tabs, scanner workflow, sale/cart flow
├── inventory_db.py            # SQLite schema + all DB operations
├── requirements.txt           # Python dependencies
├── sample_items_template.csv  # Starter CSV template for import
├── README.md                  # Setup + usage guide
└── inventory.db               # Created automatically on first run
```

## Main tabs included

1. **Master Items**
   - Search by barcode / description / SKU
   - Add, edit, delete items
   - View quantity on hand
   - Import/export CSV

2. **Item Onboarding**
   - Scan/enter barcode
   - If existing: show item
   - If new: show **NOT FOUND** + quick-add form

3. **Stock In**
   - Scan barcode and auto-lookup
   - Add received quantity + supplier/reference/date/location/notes
   - Increases quantity and logs movement history

4. **Stock Out**
   - Scan barcode and auto-lookup
   - Add quantity out + reason/reference/customer/date
   - Decreases quantity and logs movement history

5. **New Sale**
   - Scan items one-by-one (scanner + Enter)
   - Each scan adds line automatically (or increments qty if repeated)
   - Quick quantity/price edits in table
   - Customer/job fields
   - Finalize sale => auto-reduce stock + generate downloadable text receipt/invoice draft

6. **Transaction History**
   - Unified stock in/out + sale movement log
   - Filter by date, barcode, text, transaction type

## Data fields supported

- Barcode
- Product Description
- Internal SKU
- Supplier
- Category
- Cost Price
- Sell Price
- Default Location
- Quantity On Hand
- Minimum Stock
- Notes
- Optional Serial Number
- Optional Asset Number
- Optional Job Number
- Optional Install Location

## macOS setup and run

### 1) Create and activate virtual environment

```bash
cd /workspace/HA-GPT
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Run app

```bash
streamlit run app.py
```

Streamlit will print a local URL, typically `http://localhost:8501`.

## CSV import/export notes

- Import from **Master Items** tab
- Export from **Master Items** tab
- Header mapping is flexible for common variants:
  - Barcode: `barcode`, `bar code`, `code`
  - Description: `product description`, `description`, `name`, `product`
  - SKU: `internal sku`, `sku`
  - Quantity: `quantity on hand`, `qty`, `quantity`
  - Prices: `cost price`, `cost`, `sell price`, `price`, `unit price`

Use `sample_items_template.csv` as a quick starting point.

## What to test first after launch

1. **Onboarding smoke test**
   - Go to Item Onboarding
   - Scan a brand-new barcode
   - Confirm **NOT FOUND** appears
   - Quick-add the item

2. **Lookup/match test**
   - Scan same barcode again
   - Confirm item details appear immediately

3. **Stock movement test**
   - Stock In: add +5
   - Stock Out: remove -2
   - Confirm qty on hand updates correctly in Master Items

4. **Sale flow test**
   - New Sale: scan item multiple times
   - Confirm each scan adds/increments line
   - Finalize sale
   - Confirm stock reduced and receipt download appears

5. **Traceability test**
   - Open Transaction History
   - Filter by barcode and type
   - Confirm stock-in, stock-out, and sale entries are visible

## Expand later (easy next steps)

- Add GST/tax profiles
- Add customer table + saved profiles
- Add printable PDF receipts
- Add user authentication
- Package as a `.app` for easier launch on iMac
