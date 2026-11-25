"""CSV / Excel export of application records."""

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.services.applications import LOCAL_OFFSET

COLUMNS = ["Company Name", "Job Title", "City", "Job Category", "Match Score", "Match Category",
           "Application Method", "Application Date", "Application Status", "Recipient Email",
           "Company Website", "Source", "Source URL", "Application URL", "Notes"]


def rows_for(apps) -> list[list]:
    out = []
    for a in apps:
        j, c, m = a.job, a.company, a.match
        out.append([
            c.name, j.title, j.city, (j.category or "").replace("_", " ").title(), m.score if m else None,
            m.category if m else None, a.method,
            (a.applied_at + LOCAL_OFFSET).strftime("%Y-%m-%d %H:%M") if a.applied_at else None,
            a.status, a.recipient_email, c.website, j.publisher or j.source, j.source_url, j.application_url, a.notes,
        ])
    return out


def to_csv(apps) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    w.writerows(rows_for(apps))
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel shows Arabic correctly


def to_xlsx(apps, daily: list[dict] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Applications"
    ws.append(COLUMNS)
    for r in rows_for(apps):
        ws.append(r)
    _style(ws)
    if daily is not None:
        ds = wb.create_sheet("Contacted Today")
        ds.append(["Company", "Job Title", "City", "Method", "Recipient", "Applied At", "Source URL"])
        for d in daily:
            ds.append([d["company"], d["job_title"], d["city"], d["method"], d["recipient"], d["applied_at"], d["source_url"]])
        _style(ds)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _style(ws) -> None:
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1E3A8A")
    ws.freeze_panes = "A2"
    for i, col in enumerate(ws.columns, 1):
        width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[get_column_letter(i)].width = min(max(12, width + 2), 60)
