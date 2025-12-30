from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from backend.utility.packaging import collect_files_to_zip
from backend.utility.read_xlsx import iter_xlsx_rows_as_dicts


def test_collect_files_to_zip_creates_archive(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("hello")
    second.write_text("world")

    zip_path = collect_files_to_zip([first, second], tmp_path / "out.zip")

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert names == {"first.txt", "second.txt"}


def test_collect_files_to_zip_errors_on_missing_file(tmp_path):
    missing = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError):
        collect_files_to_zip([missing], tmp_path / "out.zip")


def test_iter_xlsx_rows_as_dicts_yields_rows(tmp_path):
    workbook = Workbook()
    ws = workbook.active
    ws.append(["Head Office", "Customer Number", "Email"])
    ws.append(["ACME", "123", "a@example.com"])
    ws.append([None, None, None])  # blank row should be skipped
    ws.append(["Beta", "456", "b@example.com"])

    xlsx_path = tmp_path / "clients.xlsx"
    workbook.save(xlsx_path)

    rows = list(iter_xlsx_rows_as_dicts(str(xlsx_path)))

    assert rows == [
        {"Head Office": "ACME", "Customer Number": "123", "Email": "a@example.com"},
        {"Head Office": "Beta", "Customer Number": "456", "Email": "b@example.com"},
    ]
