from pathlib import Path

import pytest

from app import sale_cart_line
from inventory_db import InventoryDB, Item


def test_unknown_barcode_quick_add_preserves_pending_quantity() -> None:
    line = sale_cart_line(
        barcode="9312345678901",
        product_description="Unknown quick-add item",
        quantity=7,
        unit_price=12.50,
    )

    assert line == {
        "barcode": "9312345678901",
        "product_description": "Unknown quick-add item",
        "quantity": 7,
        "unit_price": 12.50,
        "line_total": 87.50,
    }


def test_failed_multi_line_checkout_does_not_leave_partial_sale_or_stock_changes(tmp_path: Path) -> None:
    db = InventoryDB(tmp_path / "inventory.db")
    db.upsert_item(Item(barcode="KNOWN-1", product_description="Known item", sell_price=5.0, quantity_on_hand=10))
    customer = {"customer_name": "Test Customer"}
    cart = [
        {
            "barcode": "KNOWN-1",
            "product_description": "Known item",
            "quantity": 2,
            "unit_price": 5.0,
            "line_total": 10.0,
        },
        {
            "barcode": "MISSING-2",
            "product_description": "Missing item",
            "quantity": 1,
            "unit_price": 3.0,
            "line_total": 3.0,
        },
    ]

    with pytest.raises(ValueError, match="Missing barcode during checkout: MISSING-2"):
        db.create_sale(cart, customer, "2026-10-04")

    assert db.get_item("KNOWN-1")["quantity_on_hand"] == 10
    assert db.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM sale_lines").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] == 0

    # This later commit should not persist any partial work from the failed checkout.
    db.upsert_item(Item(barcode="AFTER", product_description="Later item", quantity_on_hand=1))

    assert db.get_item("KNOWN-1")["quantity_on_hand"] == 10
    assert db.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM sale_lines").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] == 0
