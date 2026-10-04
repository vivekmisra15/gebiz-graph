"""GeBIZ profiling v2.

Usage (from the project folder): python helpers/profile_gebiz_v2.py gebiz.csv

Prints every check needed to freeze schema v0.2 and writes
sample_150_tenders.csv (150 distinct tenders) for hand-labelling the draft
taxonomy. Read-only on the source CSV. One-off: re-running rewrites the unlabelled
sample in the current folder.
"""
import sys

import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 70)
pd.set_option("display.max_rows", 60)

path = sys.argv[1] if len(sys.argv) > 1 else "gebiz.csv"
df = pd.read_csv(path)
df["amt"] = pd.to_numeric(df["awarded_amt"], errors="coerce")
# Dates in this file are DD/MM/YYYY. Explicit format avoids silent day/month swaps.
df["date"] = pd.to_datetime(df["award_date"], format="%d/%m/%Y", errors="coerce")
month, year = df["date"].dt.month, df["date"].dt.year
# Singapore fiscal year starts 1 April; labelled by its starting calendar year.
df["fy"] = year.where(month >= 4, year - 1)


def section(title):
    print("\n" + "=" * 8 + " " + title + " " + "=" * 8)


section("A. BASICS")
print("rows:", len(df), "| distinct tender_no:", df["tender_no"].nunique())
print("unparseable dates:", df["date"].isna().sum())
print("date range:", df["date"].min(), "to", df["date"].max())
print("rows per fiscal year:")
print(df["fy"].value_counts().sort_index())

section("B. STATUS vs ZERO AMOUNT vs BLANK SUPPLIER")
df["is_zero"] = df["amt"] == 0
df["blank_supplier"] = df["supplier_name"].isna() | (
    df["supplier_name"].astype(str).str.strip() == ""
)
print(pd.crosstab(df["tender_detail_status"], df["is_zero"], margins=True))
print()
print(pd.crosstab(df["tender_detail_status"], df["blank_supplier"], margins=True))
cols = ["tender_no", "agency", "tender_detail_status", "supplier_name", "amt"]
odd = df[df["is_zero"] & (df["tender_detail_status"] != "Awarded to No Suppliers")]
print("\nzero-amount rows NOT marked 'Awarded to No Suppliers':", len(odd))
print(odd[cols].head(10).to_string())
odd2 = df[~df["is_zero"] & (df["tender_detail_status"] == "Awarded to No Suppliers")]
print("\n'Awarded to No Suppliers' rows with non-zero amount:", len(odd2))
print(odd2[cols].head(10).to_string())

section("C. TENDER-LEVEL CONSISTENCY")
g = df.groupby("tender_no")
for col in ["tender_detail_status", "tender_description", "agency", "award_date"]:
    n = (g[col].nunique() > 1).sum()
    print(f"tenders with more than one distinct {col}: {n}")
multi_status = g["tender_detail_status"].nunique()
examples = multi_status[multi_status > 1].index[:3]
if len(examples):
    print("\nexample tenders with mixed statuses:")
    print(
        df[df["tender_no"].isin(examples)][
            ["tender_no", "tender_detail_status", "supplier_name", "amt"]
        ].to_string()
    )

section("D. DUPLICATES")
all_cols = [
    "tender_no", "tender_description", "agency", "award_date",
    "tender_detail_status", "supplier_name", "awarded_amt",
]
print("rows in fully duplicated groups:", df.duplicated(subset=all_cols, keep=False).sum())
pair_dup = df.duplicated(subset=["tender_no", "supplier_name"], keep=False)
print("rows sharing (tender_no, supplier_name) with another row:", pair_dup.sum())
print(df[pair_dup].groupby("tender_detail_status").size())
print(
    df[pair_dup]
    .sort_values(["tender_no", "supplier_name"])[
        ["tender_no", "supplier_name", "tender_detail_status", "amt"]
    ]
    .head(12)
    .to_string()
)

section("E. AMOUNTS")
print("top 10 rows by amount:")
print(
    df.nlargest(10, "amt")[
        ["tender_no", "agency", "supplier_name", "amt", "tender_description"]
    ].to_string()
)
total = df["amt"].sum()
print("\ntotal, all rows: S$ {:,.0f}".format(total))
print("total, amt > 0:  S$ {:,.0f}".format(df.loc[df["amt"] > 0, "amt"].sum()))
print("share of total held by top 10 rows: {:.1%}".format(df["amt"].nlargest(10).sum() / total))
sizes = g.size()
print("\nrows per tender, multi-row tenders only:")
print(sizes[sizes > 1].describe())
elig = (df["tender_detail_status"] != "Awarded to No Suppliers") & (df["amt"] > 0)
print("\nCANDIDATE spend_eligible rows:", elig.sum(), "| excluded:", (~elig).sum())
print("candidate eligible spend by fiscal year:")
print(df[elig].groupby("fy")["amt"].sum().map("S$ {:,.0f}".format))

section("F. TAXONOMY SAMPLE")
tenders = df.drop_duplicates("tender_no")[["tender_no", "tender_description", "agency"]]
sample = tenders.sample(150, random_state=42).copy()
sample["my_category"] = ""
sample["notes"] = ""
sample.to_csv("sample_150_tenders.csv", index=False)
print("distinct tenders:", len(tenders), "| wrote sample_150_tenders.csv (150 distinct tenders)")

section("G. CHECK: 'Awarded to No Suppliers' rows")
print(df[df["tender_detail_status"] == "Awarded to No Suppliers"]["supplier_name"].value_counts().head(10))
print(((df["supplier_name"].str.strip().str.lower() == "unknown")
       & (df["tender_detail_status"] != "Awarded to No Suppliers")).sum())