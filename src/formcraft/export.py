# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""CSV and Excel export.

An alternative to the Google Sheets link: the same data, as a file you own,
with no third party involved.

Exports include *archived* questions. A question you deleted from the form
still has answers attached to it in past responses, and silently dropping
those columns would lose real data.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

TIMESTAMP_HEADER = "Submitted at"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _stamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def _columns(questions: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(question_id, header) pairs. Archived questions are marked, not hidden."""
    columns = []
    for question in questions:
        label = question["label"]
        if question.get("archived"):
            label = f"{label} (removed)"
        columns.append((question["id"], label))
    return columns


def to_csv(questions: list[dict[str, Any]], responses: list[dict[str, Any]]) -> bytes:
    columns = _columns(questions)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([TIMESTAMP_HEADER] + [header for _, header in columns])

    for response in reversed(responses):  # oldest first reads better in a sheet
        payload = response["payload"]
        writer.writerow(
            [_stamp(response["submitted_at"])]
            + [_cell(payload.get(qid)) for qid, _ in columns]
        )

    # UTF-8 BOM: without it Excel on Windows mangles non-ASCII in CSV.
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def to_xlsx(
    title: str, questions: list[dict[str, Any]], responses: list[dict[str, Any]]
) -> bytes:
    import xlsxwriter

    columns = _columns(questions)
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True, "constant_memory": True})

    # Sheet names cannot exceed 31 chars or contain []:*?/\
    safe = "".join(c for c in title if c not in "[]:*?/\\")[:31] or "Responses"
    sheet = workbook.add_worksheet(safe)

    header_fmt = workbook.add_format(
        {
            "bold": True,
            "bg_color": "#F4F4F7",
            "border": 1,
            "border_color": "#D2D2DE",
            "text_wrap": True,
            "valign": "top",
        }
    )
    stamp_fmt = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm", "valign": "top"})
    cell_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})

    headers = [TIMESTAMP_HEADER] + [header for _, header in columns]
    for index, header in enumerate(headers):
        sheet.write(0, index, header, header_fmt)

    for row, response in enumerate(reversed(responses), start=1):
        payload = response["payload"]
        submitted = response["submitted_at"]
        if isinstance(submitted, datetime):
            sheet.write_datetime(row, 0, submitted.replace(tzinfo=None), stamp_fmt)
        else:
            sheet.write(row, 0, _stamp(submitted), cell_fmt)
        for offset, (qid, _) in enumerate(columns, start=1):
            sheet.write(row, offset, _cell(payload.get(qid)), cell_fmt)

    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(len(responses), 1), len(headers) - 1)
    sheet.set_column(0, 0, 18)
    for index in range(1, len(headers)):
        sheet.set_column(index, index, 28)

    workbook.close()
    return buffer.getvalue()


def filename(title: str, extension: str) -> str:
    stem = "".join(c if c.isalnum() or c in "-_ " else "" for c in title).strip()
    stem = (stem or "responses").replace(" ", "-").lower()
    return f"{stem}-{datetime.now().strftime('%Y%m%d')}.{extension}"
