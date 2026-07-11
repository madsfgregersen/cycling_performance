import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

print("DEBUG env var names seen by container:", sorted(os.environ.keys()), flush=True)
print("DEBUG project:", os.environ.get("RAILWAY_PROJECT_NAME"), flush=True)
print("DEBUG environment:", os.environ.get("RAILWAY_ENVIRONMENT_NAME"), flush=True)
print("DEBUG service:", os.environ.get("RAILWAY_SERVICE_NAME"), flush=True)

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
