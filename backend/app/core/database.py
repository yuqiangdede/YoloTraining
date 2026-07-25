from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)
        # The project uses create_all rather than Alembic migrations. Additive
        # columns keep existing studio databases usable after upgrades.
        inspector = inspect(self.engine)
        additions = {
            "datasets": {
                "prelabel_model_path": "VARCHAR(500)",
                "prelabel_mode": "VARCHAR(20) DEFAULT 'yolo'",
                "prelabel_confidence": "FLOAT DEFAULT 0.25",
            },
            "prelabel_jobs": {"dataset_id": "VARCHAR(36)"},
            "export_jobs": {"progress": "INTEGER DEFAULT 0"},
            "model_artifacts": {"training_quality_json": "TEXT DEFAULT '{}'"},
            "dataset_versions": {
                "parent_version_id": "VARCHAR(36)",
                "quality_report_json": "TEXT DEFAULT '{}'",
                "source_json": "TEXT DEFAULT '{}'",
            },
        }
        with self.engine.begin() as connection:
            for table, columns in additions.items():
                existing = {column["name"] for column in inspector.get_columns(table)}
                for name, definition in columns.items():
                    if name not in existing:
                        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))

    def session(self) -> Session:
        return self.sessions()
