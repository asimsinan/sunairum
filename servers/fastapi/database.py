import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@db:5432/pptmaster")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_schema(target_engine=None, target_metadata=None) -> list[str]:
    """Create missing tables, then add columns missing from existing tables.

    `metadata.create_all` only ever creates whole tables, so a column added to a
    model never reached a database that already had the table: every query then
    failed on the unknown column. This adds those columns instead of requiring a
    migration tool for a two-table schema.

    Deliberately narrow: it only ADDs columns. Type changes, drops, renames and
    constraint changes are not handled and still need doing by hand.
    """
    target_engine = target_engine or engine
    target_metadata = target_metadata if target_metadata is not None else Base.metadata
    target_metadata.create_all(bind=target_engine)
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []
    with target_engine.begin() as connection:
        for table in target_metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                column_type = column.type.compile(dialect=target_engine.dialect)
                clause = f'ADD COLUMN "{column.name}" {column_type}'
                if column.server_default is not None:
                    default = column.server_default.arg
                    clause += f" DEFAULT '{default}'"
                connection.execute(text(f'ALTER TABLE "{table.name}" {clause}'))
                added.append(f"{table.name}.{column.name}")
    if added:
        print(f"[schema] added missing column(s): {', '.join(added)}")
    return added

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
