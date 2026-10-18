"""Read-only summaries of expenses.csv using pandas.

The CSV has the columns: date, category, amount, note
Example row: 2026-09-27,grocery,330.0,Nesto
"""

import re
from pathlib import Path

import pandas as pd

EXPENSES_FILE = Path("expenses.csv")
REQUIRED_COLUMNS = {"date", "category", "amount"}
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")  # e.g. 2026-09


def load_expenses(path=EXPENSES_FILE):
    """Read the CSV into a DataFrame with real dates and numbers.

    Raises ValueError if the file is missing or has bad data.
    """
    path = Path(path)
    if not path.exists():
        raise ValueError(f"No expenses file found at {path}.")

    expenses = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(expenses.columns)
    if missing:
        raise ValueError(f"expenses.csv is missing column(s): {sorted(missing)}")

    # Turn text into proper types; bad values raise ValueError.
    expenses["date"] = pd.to_datetime(expenses["date"], format="%Y-%m-%d")
    expenses["amount"] = pd.to_numeric(expenses["amount"])
    return expenses


def summarize_expenses(summary_type, month=None, path=EXPENSES_FILE):
    """Return a summary dictionary.

    summary_type: "total" for one number, "by_category" for a total per category.
    month: optional "YYYY-MM" to only include that month; None means all expenses.
    """
    if summary_type not in ("total", "by_category"):
        raise ValueError("summary_type must be 'total' or 'by_category'.")

    expenses = load_expenses(path)
    # Every month in the file, e.g. ["2026-08", "2026-09"], so Claude
    # knows what's available if the requested month has no data.
    available_months = sorted(expenses["date"].dt.strftime("%Y-%m").unique())

    if month is not None:
        if not MONTH_PATTERN.match(month):
            raise ValueError(f"Month must look like 'YYYY-MM', got {month!r}.")
        expenses = expenses[expenses["date"].dt.strftime("%Y-%m") == month]

    summary = {
        "month": month or "all",
        "number_of_expenses": len(expenses),
        "total": round(float(expenses["amount"].sum()), 2),
        "available_months": available_months,
    }
    if summary_type == "by_category":
        per_category = (
            expenses.groupby("category")["amount"].sum().sort_values(ascending=False)
        )
        summary["by_category"] = {
            category: round(float(amount), 2)
            for category, amount in per_category.items()
        }
    return summary
