"""
Seed commodities and mandis (idempotent).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base
from app.ingestion.mandi_geocoding import COMMODITY_SEED_DATA, MANDI_SEED_DATA
from app.models.commodity import Commodity, Mandi

def main():
    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    print("Seeding commodities...")
    for c in COMMODITY_SEED_DATA:
        existing = db.execute(select(Commodity).where(Commodity.slug == c["slug"])).scalar_one_or_none()
        if not existing:
            db.add(Commodity(name=c["name"], slug=c["slug"]))
            
    print("Seeding mandis...")
    for m in MANDI_SEED_DATA:
        existing = db.execute(select(Mandi).where(Mandi.name == m["name"])).scalar_one_or_none()
        if not existing:
            db.add(Mandi(**m))
        else:
            # Update lat/long in case they changed
            existing.latitude = m["latitude"]
            existing.longitude = m["longitude"]
            existing.state = m["state"]
            existing.district = m["district"]
        
    db.commit()
    db.close()
    print("Seed complete.")

if __name__ == "__main__":
    main()
