"""
AgroPredict - CSV Import Script

Imports commodity price data from CSV files (data.gov.in or Kaggle format)
into the MySQL database.

Usage:
    python scripts/import_csv.py path/to/file.csv
    python scripts/import_csv.py path/to/file.csv --filter-state "Tamil Nadu"
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, select
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.mysql import insert as mysql_insert
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base
from app.ingestion.mandi_geocoding import COMMODITY_SEED_DATA, MANDI_SEED_DATA
from app.models.commodity import Commodity, Mandi, PriceObservation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("import_csv")

# Map CSV commodity names to our slugs
COMMODITY_NAME_TO_SLUG = {
    "onion": "onion",
    "potato": "potato",
    "tomato": "tomato",
    "arhar (tur/red gram)(whole)": "tur_dal",
    "arhar(tur/red gram)(whole)": "tur_dal",
    "arhar dal": "tur_dal",
    "tur dal": "tur_dal",
    "tur (arhar)": "tur_dal",
    "arhar": "tur_dal",
}

# Map CSV market names to our mandi names
# We do fuzzy matching, so this maps substrings
MARKET_NAME_MATCHES = {
    "sooramangalam": "Sooramangalam",
    "ammapet": "Ammapet",
    "thathakapatti": "Thathakapatti",
}


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date from various formats."""
    if not date_str or pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def parse_price(val) -> Optional[float]:
    """Parse price value."""
    if val is None or pd.isna(val):
        return None
    try:
        v = float(val)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def find_matching_mandi(market_name: str) -> Optional[str]:
    """Find our mandi name from a CSV market name."""
    market_lower = market_name.lower().strip()
    for key, mandi_name in MARKET_NAME_MATCHES.items():
        if key in market_lower:
            return mandi_name
    return None


def find_commodity_slug(commodity_name: str) -> Optional[str]:
    """Find our commodity slug from a CSV commodity name."""
    name_lower = commodity_name.lower().strip()
    # Direct match
    if name_lower in COMMODITY_NAME_TO_SLUG:
        return COMMODITY_NAME_TO_SLUG[name_lower]
    # Partial match
    for key, slug in COMMODITY_NAME_TO_SLUG.items():
        if key in name_lower or name_lower in key:
            return slug
    return None


def import_csv(csv_path: str, filter_state: Optional[str] = None):
    """Import a CSV file into the database."""
    logger.info(f"Loading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    logger.info(f"Total rows in CSV: {len(df)}")
    logger.info(f"Columns: {list(df.columns)}")

    # Normalize column names
    col_map = {}
    for col in df.columns:
        col_lower = col.lower().strip().replace(" ", "_")
        if "state" in col_lower:
            col_map[col] = "state"
        elif "district" in col_lower:
            col_map[col] = "district"
        elif "market" in col_lower:
            col_map[col] = "market"
        elif "commodity" in col_lower:
            if "code" in col_lower:
                col_map[col] = "commodity_code"
            else:
                col_map[col] = "commodity"
        elif "variety" in col_lower:
            col_map[col] = "variety"
        elif "modal" in col_lower and "price" in col_lower:
            col_map[col] = "modal_price"
        elif "min" in col_lower and "price" in col_lower:
            col_map[col] = "min_price"
        elif "max" in col_lower and "price" in col_lower:
            col_map[col] = "max_price"
        elif "date" in col_lower or "arrival" in col_lower:
            col_map[col] = "date"

    df = df.rename(columns=col_map)
    logger.info(f"Normalized columns: {list(df.columns)}")

    # Filter by state if specified
    if filter_state and "state" in df.columns:
        df = df[df["state"].str.contains(filter_state, case=False, na=False)]
        logger.info(f"After state filter ({filter_state}): {len(df)} rows")

    # Filter for our commodities
    if "commodity" in df.columns:
        commodity_mask = df["commodity"].str.lower().apply(
            lambda x: find_commodity_slug(str(x)) is not None if pd.notna(x) else False
        )
        df = df[commodity_mask]
        logger.info(f"After commodity filter: {len(df)} rows")

    # Filter for our markets
    if "market" in df.columns:
        market_mask = df["market"].str.lower().apply(
            lambda x: find_matching_mandi(str(x)) is not None if pd.notna(x) else False
        )
        df = df[market_mask]
        logger.info(f"After market filter: {len(df)} rows")

    if len(df) == 0:
        logger.warning("No matching rows found after filtering!")
        # Show what commodities and markets exist for debugging
        if "commodity" in pd.read_csv(csv_path).rename(columns=col_map).columns:
            raw = pd.read_csv(csv_path).rename(columns=col_map)
            if filter_state and "state" in raw.columns:
                raw = raw[raw["state"].str.contains(filter_state, case=False, na=False)]
            logger.info(f"Available commodities: {raw['commodity'].unique()[:20]}")
            if "market" in raw.columns:
                logger.info(f"Available markets (first 20): {raw['market'].unique()[:20]}")
        return

    # Connect to DB
    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    # Ensure seed data exists
    for c_data in COMMODITY_SEED_DATA:
        existing = db.execute(
            select(Commodity).where(Commodity.slug == c_data["slug"])
        ).scalar_one_or_none()
        if not existing:
            db.add(Commodity(name=c_data["name"], slug=c_data["slug"]))
    for m_data in MANDI_SEED_DATA:
        existing = db.execute(
            select(Mandi).where(
                Mandi.name == m_data["name"], Mandi.district == m_data["district"]
            )
        ).scalar_one_or_none()
        if not existing:
            db.add(Mandi(**m_data))
    db.commit()

    # Load lookup maps
    commodities = {c.slug: c for c in db.execute(select(Commodity)).scalars().all()}
    mandis = {m.name: m for m in db.execute(select(Mandi)).scalars().all()}

    # Insert records
    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        # Parse date
        obs_date = parse_date(row.get("date", ""))
        if obs_date is None:
            skipped += 1
            continue

        # Find commodity
        slug = find_commodity_slug(str(row.get("commodity", "")))
        if not slug or slug not in commodities:
            skipped += 1
            continue

        # Find mandi
        mandi_name = find_matching_mandi(str(row.get("market", "")))
        if not mandi_name or mandi_name not in mandis:
            skipped += 1
            continue

        commodity = commodities[slug]
        mandi = mandis[mandi_name]

        min_price = parse_price(row.get("min_price"))
        max_price = parse_price(row.get("max_price"))
        modal_price = parse_price(row.get("modal_price"))

        if modal_price is None and min_price is None:
            skipped += 1
            continue

        stmt = mysql_insert(PriceObservation).values(
            commodity_id=commodity.id,
            mandi_id=mandi.id,
            date=obs_date,
            min_price=min_price,
            max_price=max_price,
            modal_price=modal_price,
            arrival_qty=None,
        )
        stmt = stmt.on_duplicate_key_update(
            min_price=stmt.inserted.min_price,
            max_price=stmt.inserted.max_price,
            modal_price=stmt.inserted.modal_price,
        )
        db.execute(stmt)
        inserted += 1

        if inserted % 500 == 0:
            db.commit()
            logger.info(f"  Progress: {inserted} inserted, {skipped} skipped")

    db.commit()
    logger.info(f"DONE: {inserted} inserted/updated, {skipped} skipped")

    db.close()
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Import CSV commodity data")
    parser.add_argument("csv_file", help="Path to CSV file")
    parser.add_argument(
        "--filter-state",
        default="Tamil Nadu",
        help="Filter for state name (default: Tamil Nadu)",
    )
    args = parser.parse_args()
    import_csv(args.csv_file, args.filter_state)


if __name__ == "__main__":
    main()
