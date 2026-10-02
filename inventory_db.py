from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Item:
    barcode: str
    product_description: str
    internal_sku: str = ""
    supplier: str = ""
    category: str = ""
    cost_price: float = 0.0
    sell_price: float = 0.0
    default_location: str = ""
    quantity_on_hand: int = 0
    minimum_stock: int = 0
    notes: str = ""
    serial_number: str = ""
    asset_number: str = ""
    job_number: str = ""
    install_location: str = ""


class InventoryDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS items (
                barcode TEXT PRIMARY KEY,
                product_description TEXT NOT NULL,
                internal_sku TEXT DEFAULT '',
                supplier TEXT DEFAULT '',
                category TEXT DEFAULT '',
                cost_price REAL DEFAULT 0,
                sell_price REAL DEFAULT 0,
                default_location TEXT DEFAULT '',
                quantity_on_hand INTEGER DEFAULT 0,
                minimum_stock INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                serial_number TEXT DEFAULT '',
                asset_number TEXT DEFAULT '',
                job_number TEXT DEFAULT '',
                install_location TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movement_type TEXT NOT NULL,
                barcode TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                reference TEXT DEFAULT '',
                partner_name TEXT DEFAULT '',
                event_date TEXT NOT NULL,
                location TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (barcode) REFERENCES items (barcode)
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_date TEXT NOT NULL,
                customer_name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                address TEXT DEFAULT '',
                job_number TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                subtotal REAL NOT NULL,
                total REAL NOT NULL,
                receipt_text TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS sale_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                barcode TEXT NOT NULL,
                product_description TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                line_total REAL NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales (id)
            );
            """
        )
        self.conn.commit()

    def upsert_item(self, item: Item) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            INSERT INTO items (
                barcode, product_description, internal_sku, supplier, category,
                cost_price, sell_price, default_location, quantity_on_hand,
                minimum_stock, notes, serial_number, asset_number, job_number,
                install_location, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(barcode) DO UPDATE SET
                product_description = excluded.product_description,
                internal_sku = excluded.internal_sku,
                supplier = excluded.supplier,
                category = excluded.category,
                cost_price = excluded.cost_price,
                sell_price = excluded.sell_price,
                default_location = excluded.default_location,
                quantity_on_hand = excluded.quantity_on_hand,
                minimum_stock = excluded.minimum_stock,
                notes = excluded.notes,
                serial_number = excluded.serial_number,
                asset_number = excluded.asset_number,
                job_number = excluded.job_number,
                install_location = excluded.install_location,
                updated_at = excluded.updated_at
            """,
            (
                item.barcode,
                item.product_description,
                item.internal_sku,
                item.supplier,
                item.category,
                item.cost_price,
                item.sell_price,
                item.default_location,
                item.quantity_on_hand,
                item.minimum_stock,
                item.notes,
                item.serial_number,
                item.asset_number,
                item.job_number,
                item.install_location,
                now,
                now,
            ),
        )
        self.conn.commit()

    def get_item(self, barcode: str) -> sqlite3.Row | None:
        cur = self.conn.execute("SELECT * FROM items WHERE barcode = ?", (barcode.strip(),))
        return cur.fetchone()

    def delete_item(self, barcode: str) -> None:
        self.conn.execute("DELETE FROM items WHERE barcode = ?", (barcode,))
        self.conn.commit()

    def search_items(self, search: str = "") -> list[sqlite3.Row]:
        if not search.strip():
            cur = self.conn.execute("SELECT * FROM items ORDER BY product_description")
            return cur.fetchall()
        like = f"%{search.strip()}%"
        cur = self.conn.execute(
            """
            SELECT * FROM items
            WHERE barcode LIKE ? OR product_description LIKE ? OR internal_sku LIKE ?
            ORDER BY product_description
            """,
            (like, like, like),
        )
        return cur.fetchall()

    def adjust_stock(
        self,
        barcode: str,
        quantity_change: int,
        movement_type: str,
        reference: str,
        partner_name: str,
        event_date: str,
        location: str,
        notes: str,
    ) -> None:
        item = self.get_item(barcode)
        if item is None:
            raise ValueError("Barcode not found")

        new_qty = int(item["quantity_on_hand"]) + quantity_change
        if new_qty < 0:
            raise ValueError("Insufficient stock")

        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "UPDATE items SET quantity_on_hand = ?, updated_at = ? WHERE barcode = ?",
            (new_qty, now, barcode),
        )
        self.conn.execute(
            """
            INSERT INTO stock_movements (
                movement_type, barcode, quantity, reference, partner_name,
                event_date, location, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                movement_type,
                barcode,
                quantity_change,
                reference,
                partner_name,
                event_date,
                location,
                notes,
                now,
            ),
        )
        self.conn.commit()

    def create_sale(self, cart_lines: list[dict[str, Any]], customer: dict[str, str], sale_date: str) -> tuple[int, str]:
        if not cart_lines:
            raise ValueError("Cart is empty")

        subtotal = round(sum(line["line_total"] for line in cart_lines), 2)
        total = subtotal
        receipt_text = self._build_receipt(cart_lines, customer, sale_date, subtotal, total)

        cur = self.conn.execute(
            """
            INSERT INTO sales (
                sale_date, customer_name, phone, address, job_number, notes,
                subtotal, total, receipt_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                customer.get("customer_name", ""),
                customer.get("phone", ""),
                customer.get("address", ""),
                customer.get("job_number", ""),
                customer.get("notes", ""),
                subtotal,
                total,
                receipt_text,
            ),
        )
        sale_id = int(cur.lastrowid)

        now = datetime.utcnow().isoformat()
        for line in cart_lines:
            item = self.get_item(line["barcode"])
            if item is None:
                raise ValueError(f"Missing barcode during checkout: {line['barcode']}")
            if int(item["quantity_on_hand"]) < int(line["quantity"]):
                raise ValueError(f"Not enough stock for {line['barcode']}")

            self.conn.execute(
                """
                INSERT INTO sale_lines (sale_id, barcode, product_description, quantity, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sale_id,
                    line["barcode"],
                    line["product_description"],
                    line["quantity"],
                    line["unit_price"],
                    line["line_total"],
                ),
            )
            self.conn.execute(
                "UPDATE items SET quantity_on_hand = quantity_on_hand - ?, updated_at = ? WHERE barcode = ?",
                (line["quantity"], now, line["barcode"]),
            )
            self.conn.execute(
                """
                INSERT INTO stock_movements (
                    movement_type, barcode, quantity, reference, partner_name,
                    event_date, location, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "sale",
                    line["barcode"],
                    -int(line["quantity"]),
                    f"SALE-{sale_id}",
                    customer.get("customer_name", ""),
                    sale_date,
                    "",
                    customer.get("notes", ""),
                    now,
                ),
            )

        self.conn.commit()
        return sale_id, receipt_text

    def get_transactions(
        self,
        start_date: str,
        end_date: str,
        barcode: str,
        text_search: str,
        tx_type: str,
    ) -> list[sqlite3.Row]:
        query = (
            "SELECT movement_type, barcode, quantity, reference, partner_name, event_date, location, notes, created_at "
            "FROM stock_movements WHERE date(event_date) BETWEEN date(?) AND date(?)"
        )
        params: list[Any] = [start_date, end_date]

        if barcode.strip():
            query += " AND barcode LIKE ?"
            params.append(f"%{barcode.strip()}%")

        if text_search.strip():
            query += " AND (reference LIKE ? OR partner_name LIKE ? OR notes LIKE ?)"
            like = f"%{text_search.strip()}%"
            params.extend([like, like, like])

        if tx_type != "all":
            query += " AND movement_type = ?"
            params.append(tx_type)

        query += " ORDER BY event_date DESC, id DESC"
        cur = self.conn.execute(query, tuple(params))
        return cur.fetchall()

    def import_items_csv(self, csv_path: Path) -> tuple[int, int]:
        inserted = 0
        skipped = 0
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return inserted, skipped

            for raw in reader:
                row = {str(k).strip().lower(): (v or "").strip() for k, v in raw.items() if k}
                barcode = self._pick(row, ["barcode", "bar code", "code"]) 
                if not barcode:
                    skipped += 1
                    continue

                item = Item(
                    barcode=barcode,
                    product_description=self._pick(
                        row,
                        ["product description", "description", "name", "product"],
                    )
                    or "Unnamed Item",
                    internal_sku=self._pick(row, ["internal sku", "sku"]),
                    supplier=self._pick(row, ["supplier"]),
                    category=self._pick(row, ["category"]),
                    cost_price=self._safe_float(self._pick(row, ["cost price", "cost"])),
                    sell_price=self._safe_float(self._pick(row, ["sell price", "price", "unit price"])),
                    default_location=self._pick(row, ["default location", "location"]),
                    quantity_on_hand=self._safe_int(self._pick(row, ["quantity on hand", "qty", "quantity"])),
                    minimum_stock=self._safe_int(self._pick(row, ["minimum stock", "min stock"])),
                    notes=self._pick(row, ["notes"]),
                    serial_number=self._pick(row, ["serial number"]),
                    asset_number=self._pick(row, ["asset number"]),
                    job_number=self._pick(row, ["job number"]),
                    install_location=self._pick(row, ["install location"]),
                )
                self.upsert_item(item)
                inserted += 1

        return inserted, skipped

    def export_items_csv_text(self) -> str:
        rows = self.search_items()
        headers = [
            "barcode",
            "product_description",
            "internal_sku",
            "supplier",
            "category",
            "cost_price",
            "sell_price",
            "default_location",
            "quantity_on_hand",
            "minimum_stock",
            "notes",
            "serial_number",
            "asset_number",
            "job_number",
            "install_location",
        ]

        output: list[str] = [",".join(headers)]
        for row in rows:
            values = [str(row[h]) for h in headers]
            escaped = []
            for v in values:
                if "," in v or '"' in v:
                    escaped.append('"' + v.replace('"', '""') + '"')
                else:
                    escaped.append(v)
            output.append(",".join(escaped))
        return "\n".join(output)

    @staticmethod
    def _pick(row: dict[str, str], keys: list[str]) -> str:
        for key in keys:
            if row.get(key):
                return row[key]
        return ""

    @staticmethod
    def _safe_float(value: str) -> float:
        try:
            return float(value) if value else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _safe_int(value: str) -> int:
        try:
            return int(float(value)) if value else 0
        except ValueError:
            return 0

    @staticmethod
    def _build_receipt(
        cart_lines: list[dict[str, Any]],
        customer: dict[str, str],
        sale_date: str,
        subtotal: float,
        total: float,
    ) -> str:
        lines = [
            "SIMPLE SALES RECEIPT / INVOICE DRAFT",
            f"Date: {sale_date}",
            f"Customer: {customer.get('customer_name', '')}",
            f"Phone: {customer.get('phone', '')}",
            f"Address: {customer.get('address', '')}",
            f"Job Number: {customer.get('job_number', '')}",
            "-" * 60,
            "Barcode | Description | Qty | Unit | Line Total",
            "-" * 60,
        ]

        for line in cart_lines:
            lines.append(
                f"{line['barcode']} | {line['product_description']} | {line['quantity']} | "
                f"{line['unit_price']:.2f} | {line['line_total']:.2f}"
            )

        lines.extend(
            [
                "-" * 60,
                f"Subtotal: {subtotal:.2f}",
                f"Total: {total:.2f}",
                f"Notes: {customer.get('notes', '')}",
            ]
        )
        return "\n".join(lines)
