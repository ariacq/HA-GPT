from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from inventory_db import InventoryDB, Item

DB_PATH = Path("inventory.db")
BARCODE_MIN_LENGTH = 7
QTY_MAX_LENGTH = 3


@st.cache_resource
def get_db() -> InventoryDB:
    return InventoryDB(DB_PATH)


def item_form(prefix: str, barcode: str = "") -> Item:
    return Item(
        barcode=st.text_input("Barcode", value=barcode, key=f"{prefix}_barcode").strip(),
        product_description=st.text_input("Product Description", key=f"{prefix}_desc").strip(),
        internal_sku=st.text_input("Internal SKU", key=f"{prefix}_sku").strip(),
        supplier=st.text_input("Supplier", key=f"{prefix}_supplier").strip(),
        category=st.text_input("Category", key=f"{prefix}_category").strip(),
        cost_price=st.number_input("Cost Price", min_value=0.0, step=0.01, key=f"{prefix}_cost"),
        sell_price=st.number_input("Sell Price", min_value=0.0, step=0.01, key=f"{prefix}_sell"),
        default_location=st.text_input("Default Location", key=f"{prefix}_loc").strip(),
        quantity_on_hand=st.number_input("Quantity On Hand", min_value=0, step=1, key=f"{prefix}_qty"),
        minimum_stock=st.number_input("Minimum Stock", min_value=0, step=1, key=f"{prefix}_min"),
        notes=st.text_area("Notes", key=f"{prefix}_notes").strip(),
        serial_number=st.text_input("Optional Serial Number", key=f"{prefix}_serial").strip(),
        asset_number=st.text_input("Optional Asset Number", key=f"{prefix}_asset").strip(),
        job_number=st.text_input("Optional Job Number", key=f"{prefix}_job").strip(),
        install_location=st.text_input("Optional Install Location", key=f"{prefix}_install").strip(),
    )


def line_items_table(lines: list[dict]) -> pd.DataFrame:
    if not lines:
        return pd.DataFrame(columns=["barcode", "product_description", "quantity", "unit_price", "line_total"])
    return pd.DataFrame(lines)


def set_scan_message(level: str, message: str) -> None:
    st.session_state.scan_feedback = {"level": level, "message": message}


def consume_scan_feedback() -> None:
    feedback = st.session_state.pop("scan_feedback", None)
    if not feedback:
        return
    if feedback["level"] == "success":
        st.success(feedback["message"])
    elif feedback["level"] == "error":
        st.error(feedback["message"])
    else:
        st.info(feedback["message"])


def handle_scan_input(context: str) -> None:
    raw = st.session_state.get("scan_input", "").strip()
    if not raw:
        return

    if raw.isdigit() and len(raw) <= QTY_MAX_LENGTH:
        st.session_state.pending_qty = int(raw)
        st.session_state.scan_input = ""
        st.session_state[f"scan_input_{context}"] = ""
        set_scan_message("info", f"Pending Qty: {raw}")
        return
    if len(raw) <= 6:
        st.session_state.scan_input = ""
        st.session_state[f"scan_input_{context}"] = ""
        return

    qty = st.session_state.pending_qty if st.session_state.pending_qty is not None else 1
    barcode = raw
    db = get_db()

    if context == "stock_in":
        item = db.get_item(barcode)
        if item is None:
            set_scan_message("error", "NOT FOUND — use Item Onboarding first.")
        else:
            db.adjust_stock(
                barcode=barcode,
                quantity_change=qty,
                movement_type="stock_in",
                reference=st.session_state.get("stock_in_reference", ""),
                partner_name=st.session_state.get("stock_in_supplier", ""),
                event_date=str(st.session_state.get("stock_in_date", date.today())),
                location=st.session_state.get("stock_in_location", "") or item["default_location"],
                notes=st.session_state.get("stock_in_notes", ""),
            )
            set_scan_message("success", f"Stock in saved for {barcode} (+{qty}).")
    elif context == "stock_out":
        item = db.get_item(barcode)
        if item is None:
            set_scan_message("error", "NOT FOUND — use Item Onboarding first.")
        else:
            try:
                db.adjust_stock(
                    barcode=barcode,
                    quantity_change=-qty,
                    movement_type="stock_out",
                    reference=st.session_state.get("stock_out_reference", ""),
                    partner_name=st.session_state.get("stock_out_customer", ""),
                    event_date=str(st.session_state.get("stock_out_date", date.today())),
                    location=item["default_location"],
                    notes=f"{st.session_state.get('stock_out_reason', '')} {st.session_state.get('stock_out_notes', '')}".strip(),
                )
                set_scan_message("success", f"Stock out saved for {barcode} (-{qty}).")
            except ValueError as exc:
                set_scan_message("error", str(exc))
    else:
        found = db.get_item(barcode)
        if found is None:
            st.session_state.sale_unknown = barcode
            set_scan_message("error", "NOT FOUND — quick-add below")
        else:
            existing_line = next((l for l in st.session_state.cart if l["barcode"] == barcode), None)
            if existing_line:
                existing_line["quantity"] += qty
                existing_line["line_total"] = round(existing_line["quantity"] * existing_line["unit_price"], 2)
            else:
                unit_price = float(found["sell_price"])
                st.session_state.cart.append(
                    {
                        "barcode": barcode,
                        "product_description": found["product_description"],
                        "quantity": qty,
                        "unit_price": unit_price,
                        "line_total": round(unit_price * qty, 2),
                    }
                )
            set_scan_message("success", f"Added {barcode} x{qty}")

    st.session_state.last_barcode = barcode
    st.session_state.pending_qty = None
    st.session_state.scan_input = ""
    st.session_state[f"scan_input_{context}"] = ""


def sync_and_handle_scan(context: str) -> None:
    st.session_state.scan_input = st.session_state.get(f"scan_input_{context}", "")
    handle_scan_input(context)


def main() -> None:
    st.set_page_config(page_title="Practical Inventory App", layout="wide")
    st.title("Practical Local Inventory + Barcode Register")
    st.caption("Streamlit + SQLite. Scanner-first workflow for Mac USB barcode scanners.")

    db = get_db()
    if "cart" not in st.session_state:
        st.session_state.cart = []
    if "pending_qty" not in st.session_state:
        st.session_state.pending_qty = None
    if "scan_input" not in st.session_state:
        st.session_state.scan_input = ""
    if "last_barcode" not in st.session_state:
        st.session_state.last_barcode = ""

    tabs = st.tabs(
        [
            "Master Items",
            "Item Onboarding",
            "Stock In",
            "Stock Out",
            "New Sale",
            "Transaction History",
        ]
    )

    with tabs[0]:
        st.subheader("Master Items")
        search = st.text_input("Search barcode / description / SKU")
        rows = db.search_items(search)
        df = pd.DataFrame([dict(r) for r in rows])
        if not df.empty:
            st.dataframe(
                df[
                    [
                        "barcode",
                        "product_description",
                        "internal_sku",
                        "supplier",
                        "category",
                        "sell_price",
                        "quantity_on_hand",
                        "minimum_stock",
                        "default_location",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Add / Edit Item")
            with st.form("master_add_form"):
                item = item_form("master")
                save = st.form_submit_button("Save Item")
            if save:
                if not item.barcode:
                    st.error("Barcode is required.")
                elif not item.product_description:
                    st.error("Product Description is required.")
                else:
                    db.upsert_item(item)
                    st.success(f"Saved {item.barcode}")

        with c2:
            st.markdown("#### Delete Item")
            delete_barcode = st.text_input("Barcode to delete")
            if st.button("Delete", type="secondary"):
                if delete_barcode.strip():
                    db.delete_item(delete_barcode.strip())
                    st.warning(f"Deleted {delete_barcode.strip()}")

            st.markdown("#### CSV Import / Export")
            upload = st.file_uploader("Import items CSV", type=["csv"])
            if upload is not None and st.button("Run Import"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    tmp.write(upload.getvalue())
                    tmp_path = Path(tmp.name)
                inserted, skipped = db.import_items_csv(tmp_path)
                st.success(f"Imported/updated: {inserted}, skipped: {skipped}")

            csv_text = db.export_items_csv_text()
            st.download_button(
                "Export Items CSV",
                data=csv_text,
                file_name="items_export.csv",
                mime="text/csv",
            )

    with tabs[1]:
        st.subheader("Item Onboarding (Quick Add)")
        st.write("Scan barcode then Enter. If item exists you will see it. If not, quick-add immediately.")

        with st.form("onboard_scan_form", clear_on_submit=True):
            scan_code = st.text_input("Scanner Input", key="onboard_scan", placeholder="Scan barcode and press Enter")
            scanned = st.form_submit_button("Lookup / Prepare")

        existing = None
        if scanned and scan_code.strip():
            existing = db.get_item(scan_code.strip())
            st.session_state.onboard_last_scan = scan_code.strip()

        current_scan = st.session_state.get("onboard_last_scan", "")
        if current_scan:
            found = db.get_item(current_scan)
            if found:
                st.success("Matched existing item")
                st.json(dict(found))
            else:
                st.error("NOT FOUND — quick-add below")
                with st.form("quick_add_form"):
                    item = item_form("quick", barcode=current_scan)
                    quick_save = st.form_submit_button("Quick Save New Item")
                if quick_save:
                    if not item.product_description:
                        st.error("Product Description is required")
                    else:
                        db.upsert_item(item)
                        st.success(f"Added {item.barcode}")
                        st.session_state.onboard_last_scan = ""

    with tabs[2]:
        st.subheader("Stock In")
        if st.session_state.pending_qty:
            st.warning(f"Pending Qty: {st.session_state.pending_qty}")
        st.text_input(
            "Scan Barcode",
            key="scan_input_stock_in",
            placeholder="Type qty (e.g. 5) + Enter, then scan barcode + Enter",
            on_change=sync_and_handle_scan,
            args=("stock_in",),
        )
        st.caption(f"Last Barcode: {st.session_state.last_barcode or '-'}")
        consume_scan_feedback()

        st.text_input("Supplier", key="stock_in_supplier")
        st.text_input("Reference / Invoice", key="stock_in_reference")
        st.date_input("Date", value=date.today(), key="stock_in_date")
        st.text_input("Location", key="stock_in_location")
        st.text_input("Notes", key="stock_in_notes")

    with tabs[3]:
        st.subheader("Stock Out")
        if st.session_state.pending_qty:
            st.warning(f"Pending Qty: {st.session_state.pending_qty}")
        st.text_input(
            "Scan Barcode",
            key="scan_input_stock_out",
            placeholder="Type qty (e.g. 5) + Enter, then scan barcode + Enter",
            on_change=sync_and_handle_scan,
            args=("stock_out",),
        )
        st.caption(f"Last Barcode: {st.session_state.last_barcode or '-'}")
        consume_scan_feedback()

        st.text_input("Reason", key="stock_out_reason")
        st.text_input("Reference", key="stock_out_reference")
        st.text_input("Customer", key="stock_out_customer")
        st.date_input("Date", value=date.today(), key="stock_out_date")
        st.text_input("Notes", key="stock_out_notes")

    with tabs[4]:
        st.subheader("New Sale")
        st.write("Trade-counter flow: scan, line appears, scan next. Unknown = quick-add without losing cart.")
        if st.session_state.pending_qty:
            st.warning(f"Pending Qty: {st.session_state.pending_qty}")
        st.text_input(
            "Scan Barcode",
            key="scan_input_sale",
            placeholder="Type qty (e.g. 5) + Enter, then scan barcode + Enter",
            on_change=sync_and_handle_scan,
            args=("sale",),
        )
        st.caption(f"Last Barcode: {st.session_state.last_barcode or '-'}")
        consume_scan_feedback()

        unknown = st.session_state.get("sale_unknown", "")
        if unknown:
            st.markdown("#### Quick-add unknown barcode (without losing current sale)")
            with st.form("sale_quick_add"):
                item = item_form("salequick", barcode=unknown)
                quick_save = st.form_submit_button("Save + Add to Cart")
            if quick_save:
                if not item.product_description:
                    st.error("Product Description is required")
                else:
                    db.upsert_item(item)
                    st.session_state.cart.append(
                        {
                            "barcode": item.barcode,
                            "product_description": item.product_description,
                            "quantity": 1,
                            "unit_price": float(item.sell_price),
                            "line_total": round(float(item.sell_price), 2),
                        }
                    )
                    st.session_state.sale_unknown = ""
                    st.success(f"Created and added {item.barcode}")

        cart_df = line_items_table(st.session_state.cart)
        edited = st.data_editor(
            cart_df,
            use_container_width=True,
            num_rows="dynamic",
            disabled=["barcode", "product_description", "line_total"],
            key="cart_editor",
        )

        if not edited.empty:
            refreshed = []
            for _, row in edited.iterrows():
                qty = int(row["quantity"])
                price = float(row["unit_price"])
                refreshed.append(
                    {
                        "barcode": row["barcode"],
                        "product_description": row["product_description"],
                        "quantity": qty,
                        "unit_price": price,
                        "line_total": round(qty * price, 2),
                    }
                )
            st.session_state.cart = refreshed

        subtotal = round(sum(x["line_total"] for x in st.session_state.cart), 2)
        st.metric("Running Total", f"${subtotal:.2f}")

        st.markdown("#### Customer / Job")
        c1, c2 = st.columns(2)
        with c1:
            customer_name = st.text_input("Customer Name")
            phone = st.text_input("Phone")
            address = st.text_area("Address")
        with c2:
            job_number = st.text_input("Job Number")
            sale_notes = st.text_area("Notes")
            sale_date = st.date_input("Sale Date", value=date.today())

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Finalize Sale and Reduce Stock", type="primary"):
                customer = {
                    "customer_name": customer_name,
                    "phone": phone,
                    "address": address,
                    "job_number": job_number,
                    "notes": sale_notes,
                }
                try:
                    sale_id, receipt = db.create_sale(st.session_state.cart, customer, str(sale_date))
                    st.success(f"Sale saved. Sale ID: {sale_id}")
                    st.download_button(
                        label="Download Receipt / Invoice Draft",
                        data=receipt,
                        file_name=f"sale_{sale_id}.txt",
                        mime="text/plain",
                    )
                    st.session_state.cart = []
                except ValueError as exc:
                    st.error(str(exc))

        with b2:
            if st.button("Clear Cart"):
                st.session_state.cart = []
                st.info("Cart cleared")

    with tabs[5]:
        st.subheader("Transaction History")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            start_date = st.date_input("From", value=date.today().replace(day=1), key="tx_start")
        with c2:
            end_date = st.date_input("To", value=date.today(), key="tx_end")
        with c3:
            filter_barcode = st.text_input("Barcode Filter")
        with c4:
            tx_type = st.selectbox("Type", options=["all", "stock_in", "stock_out", "sale"])

        text_search = st.text_input("Search reference/customer/notes")
        tx_rows = db.get_transactions(str(start_date), str(end_date), filter_barcode, text_search, tx_type)
        tx_df = pd.DataFrame([dict(r) for r in tx_rows])
        if tx_df.empty:
            st.info("No transactions in selected filters.")
        else:
            st.dataframe(tx_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
