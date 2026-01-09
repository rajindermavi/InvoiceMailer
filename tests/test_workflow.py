from __future__ import annotations

import zipfile
from pathlib import Path

import backend.workflow as workflow


def test_scan_for_invoices_builds_per_client_results(monkeypatch):
    clients = ["CUST1", "CUST2"]

    def fake_get_client(**kwargs):
        val = kwargs.get("customer_number") or kwargs.get("head_office") or ""
        return [{"head_office": f"HO-{val}"}]

    def fake_get_soa_by_head_office(head_office):
        return [
            {
                "soa_file_path": f"/soa/{head_office}.pdf",
                "head_office_name": f"{head_office} Name",
            }
        ]

    def fake_get_invoices(**kwargs):
        cust = kwargs.get("customer_number", "")
        period = kwargs.get("period_month")
        return [
            {
                "tax_invoice_no": f"INV-{cust}-{period}",
                "customer_number": cust,
                "ship_name": "SHIP",
                "invoice_date": f"{period}-01",
                "inv_file_path": f"/invoices/{cust}.pdf",
            }
        ]

    monkeypatch.setattr(workflow, "get_client", fake_get_client)
    monkeypatch.setattr(workflow, "get_soa_by_head_office", fake_get_soa_by_head_office)
    monkeypatch.setattr(workflow, "get_invoices", fake_get_invoices)

    result = workflow.scan_for_invoices(clients, 2024, 5, "customer_number")

    assert set(result.keys()) == set(clients)
    entries = result["CUST1"]
    assert len(entries) == 2
    assert {entry["invoice_date"] for entry in entries} == {"2024-05-01", "2024-06-01"}
    for entry in entries:
        assert entry["customer_number"] == "CUST1"
        assert entry["head_office_name"] == "HO-CUST1 Name"
        assert entry["soa_path"] == "/soa/HO-CUST1.pdf"
        assert entry["invoice_path"] == "/invoices/CUST1.pdf"
    assert {entry["invoice_number"] for entry in entries} == {
        "INV-CUST1-2024-05",
        "INV-CUST1-2024-06",
    }


def test_prep_invoice_zips_creates_archives_and_email_payload(tmp_path, monkeypatch):
    inv1 = tmp_path / "one.pdf"
    inv2 = tmp_path / "two.pdf"
    soa = tmp_path / "soa.pdf"
    for path, content in ((inv1, "first"), (inv2, "second"), (soa, "soa")):
        path.write_text(content)

    invoices_to_ship = {
        "ACME Corp": [
            {
                "head_office_name": "ACME:Corp",
                "ship_name": "SAFE MARINE",
                "invoice_number": "INV-001",
                "invoice_date": "2024-05-01",
                "invoice_path": inv1,
                "soa_path": soa,
                "customer_number": "ACME123",
            },
            {
                "head_office_name": "ACME:Corp",
                "ship_name": "SAFE MARINE",
                "invoice_number": "INV-002",
                "invoice_date": "2024-05-02",
                "invoice_path": inv2,
                "soa_path": soa,
                "customer_number": "ACME123",
            },
        ]
    }

    monkeypatch.setattr(workflow, "get_client_email", lambda head_office=None: ["billing@example.com"])

    shipments = workflow.prep_invoice_zips(invoices_to_ship, zip_output_dir=tmp_path / "zips")

    assert len(shipments) == 1
    shipment = shipments[0]
    assert shipment["email_list"] == ["billing@example.com"]
    assert "ACME_Corp" in shipment["head_office_name"]

    zip_path = shipment["zip_path"]
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert names == {"one.pdf", "two.pdf", "soa.pdf"}
