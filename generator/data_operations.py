"""
Database operations using SQLAlchemy ORM with PostgreSQL.
Implements bulk operations and proper transaction handling.
"""

from typing import List, Dict, Tuple
from sqlalchemy import create_engine, Engine, select, update, delete, func, insert
from sqlalchemy.orm import Session, sessionmaker
from dataclasses import asdict

from generator.models import Base, Anime, ChangeLog, ManualMapping
from generator.anime_record import AnimeRecord
from generator.const import DATABASE_URL, pprint
from generator.prettyprint import Platform, Status


class ChangeSet:
    """Represents a set of changes to be applied to the database."""

    def __init__(self):
        self.inserts: List[AnimeRecord] = []
        self.updates: List[Tuple[int, AnimeRecord]] = []  # (anime_id, record)
        self.deletes: List[int] = []  # anime_ids to delete

    def total_changes(self) -> int:
        """Get total number of changes."""
        return len(self.inserts) + len(self.updates) + len(self.deletes)


class SQLAlchemyOperations:
    """High-performance database operations using SQLAlchemy ORM with PostgreSQL."""

    def __init__(self, db_path: str = DATABASE_URL):
        """Initialize with database path."""
        self.db_path = db_path
        self.engine = self._create_engine()
        self.Session = sessionmaker(bind=self.engine)
        self._create_tables()

    def _create_engine(self) -> Engine:
        """Create SQLAlchemy engine with PostgreSQL."""
        return create_engine(
            self.db_path,
            echo=False,  # Set to True for SQL debugging
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections every hour
            pool_size=10,  # Connection pool size
            max_overflow=20,  # Maximum overflow connections
        )

    def _create_tables(self) -> None:
        """Create all database tables."""
        Base.metadata.create_all(self.engine)

    def detect_changes(self, new_records: List[AnimeRecord]) -> ChangeSet:
        """Detect changes between new records and existing database."""
        pprint.print(
            Platform.SYSTEM, Status.INFO, "Detecting changes in anime records..."
        )

        changeset = ChangeSet()

        with self.Session() as session:
            # Get existing records from database
            existing_records = session.execute(
                select(Anime.id, Anime.title, Anime.myanimelist, Anime.data_hash)
            ).all()

            existing_by_mal = {
                r.myanimelist: r for r in existing_records if r.myanimelist
            }
            existing_by_title = {r.title: r for r in existing_records}

            # Track processed records
            processed_mal_ids = set()
            processed_titles = set()

            # Process new records
            for record in new_records:
                # Compute hash for change detection
                record.data_hash = record.compute_hash()

                existing_record = None

                # Try to find existing record by MAL ID first
                if record.myanimelist and record.myanimelist in existing_by_mal:
                    existing_record = existing_by_mal[record.myanimelist]
                    processed_mal_ids.add(record.myanimelist)
                # Then try by title
                elif record.title in existing_by_title:
                    existing_record = existing_by_title[record.title]
                    processed_titles.add(record.title)

                if existing_record:
                    # Check if record has changed
                    if existing_record.data_hash != record.data_hash:
                        changeset.updates.append((existing_record.id, record))
                else:
                    # New record
                    changeset.inserts.append(record)
                    if record.myanimelist:
                        processed_mal_ids.add(record.myanimelist)
                    processed_titles.add(record.title)

            # Find records to delete (existed before but not in new data)
            for existing_record in existing_records:
                should_delete = False

                if existing_record.myanimelist:
                    if existing_record.myanimelist not in processed_mal_ids:
                        should_delete = True
                elif existing_record.title not in processed_titles:
                    should_delete = True

                if should_delete:
                    changeset.deletes.append(existing_record.id)

        pprint.print(
            Platform.SYSTEM,
            Status.INFO,
            f"Changes detected: {len(changeset.inserts)} inserts, {len(changeset.updates)} updates, {len(changeset.deletes)} deletes",
        )
        return changeset

    def apply_changes(self, changeset: ChangeSet) -> None:
        """Apply changes to the database using efficient bulk operations."""
        if changeset.total_changes() == 0:
            pprint.print(Platform.SYSTEM, Status.INFO, "No changes to apply")
            return

        pprint.print(
            Platform.SYSTEM,
            Status.INFO,
            f"Applying {changeset.total_changes()} changes to database...",
        )

        with self.Session() as session:
            try:
                # Apply bulk inserts
                if changeset.inserts:
                    anime_ids = self._bulk_insert_anime_records(
                        session, changeset.inserts
                    )
                    self._bulk_log_changes(session, anime_ids, "insert")

                # Apply bulk updates
                if changeset.updates:
                    self._bulk_update_anime_records(session, changeset.updates)
                    anime_ids = [anime_id for anime_id, _ in changeset.updates]
                    self._bulk_log_changes(session, anime_ids, "update")

                # Apply bulk deletes
                if changeset.deletes:
                    self._bulk_delete_anime_records(session, changeset.deletes)
                    self._bulk_log_changes(session, changeset.deletes, "delete")

                # Commit all changes
                session.commit()
                pprint.print(
                    Platform.SYSTEM, Status.PASS, "Changes applied successfully"
                )

            except Exception as e:
                session.rollback()
                pprint.print(
                    Platform.SYSTEM, Status.FAIL, f"Failed to apply changes: {e}"
                )
                raise

    def _bulk_insert_anime_records(
        self, session: Session, records: List[AnimeRecord]
    ) -> List[int]:
        """Insert multiple anime records using PostgreSQL COPY FROM for maximum performance."""
        if not records:
            return []

        # Use COPY FROM for maximum performance - no batching needed
        return self._copy_from_insert(session, records)

    def _copy_from_insert(
        self, session: Session, records: List[AnimeRecord]
    ) -> List[int]:
        """Use PostgreSQL COPY FROM for ultra-fast bulk insert."""
        import io
        from generator.models import Anime

        # Get all column names from the Anime model, excluding auto-generated columns
        anime_columns = [
            col.name for col in Anime.__table__.columns 
            if col.name not in ("id", "created_at", "updated_at")
        ]

        # Convert records to clean dicts and collect unique identifiers for ID lookup
        record_dicts = []
        unique_identifiers = []  # (title, myanimelist) pairs for ID lookup

        for record in records:
            record_dict = asdict(record)
            # Remove None values and ensure all values are proper Python types
            clean_dict = {}
            for col_name in anime_columns:
                value = record_dict.get(col_name)
                if value is not None:
                    # Ensure the value is a proper Python type
                    if hasattr(value, "__dict__") and not isinstance(
                        value, (str, int, float, bool, list, dict)
                    ):
                        continue
                    clean_dict[col_name] = value
                else:
                    clean_dict[col_name] = None

            record_dicts.append(clean_dict)
            # Store unique identifiers for ID lookup (title is required, myanimelist is optional)
            unique_identifiers.append(
                (record.title, getattr(record, "myanimelist", None))
            )

        # Create TSV data in memory
        tsv_data = io.StringIO()

        # Write data rows (no header for COPY FROM)
        for record_dict in record_dicts:
            row_values = []
            for col_name in anime_columns:
                value = record_dict[col_name]
                if value is None:
                    row_values.append("")  # Empty string for NULL
                elif isinstance(value, str):
                    # Escape tabs and newlines in strings
                    escaped = (
                        value.replace("\t", "\\t")
                        .replace("\n", "\\n")
                        .replace("\r", "\\r")
                    )
                    row_values.append(escaped)
                else:
                    row_values.append(str(value))
            tsv_data.write("\t".join(row_values) + "\n")

        tsv_data.seek(0)

        # Use raw psycopg2 connection for COPY FROM
        raw_conn = session.connection().connection
        cursor = raw_conn.cursor()
        try:
            cursor.copy_expert(
                f"COPY anime ({','.join(anime_columns)}) FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '')",
                tsv_data,
            )
        finally:
            cursor.close()

        pprint.print(
            Platform.SYSTEM,
            Status.INFO,
            f"Bulk inserted {len(records)} records using COPY FROM",
        )

        # Get inserted IDs by querying using unique identifiers
        return self._get_inserted_ids(session, unique_identifiers)

    def _get_inserted_ids(
        self, session: Session, unique_identifiers: List[Tuple[str, str]]
    ) -> List[int]:
        """Get IDs of inserted records using unique identifiers."""
        # Build a query to get IDs for all inserted records
        # We'll use title and myanimelist as unique identifiers

        anime_ids = []

        # Process in batches to avoid huge IN clauses
        BATCH_SIZE = 1000
        for i in range(0, len(unique_identifiers), BATCH_SIZE):
            batch = unique_identifiers[i : i + BATCH_SIZE]

            # Separate records with and without myanimelist IDs
            mal_records = [
                (title, mal_id) for title, mal_id in batch if mal_id is not None
            ]
            title_only_records = [title for title, mal_id in batch if mal_id is None]

            batch_ids = []

            # Query records that have myanimelist IDs (more reliable)
            if mal_records:
                mal_ids = [mal_id for _, mal_id in mal_records]
                result = session.execute(
                    select(Anime.id).where(Anime.myanimelist.in_(mal_ids))
                )
                batch_ids.extend([row[0] for row in result])

            # Query records without myanimelist IDs (use title)
            if title_only_records:
                result = session.execute(
                    select(Anime.id).where(Anime.title.in_(title_only_records))
                )
                batch_ids.extend([row[0] for row in result])

            anime_ids.extend(batch_ids)

            # Log progress for large batches
            if len(unique_identifiers) > BATCH_SIZE:
                pprint.print(
                    Platform.SYSTEM,
                    Status.INFO,
                    f"Retrieved IDs for batch {i // BATCH_SIZE + 1}/{(len(unique_identifiers) + BATCH_SIZE - 1) // BATCH_SIZE}",
                )

        pprint.print(
            Platform.SYSTEM,
            Status.INFO,
            f"Retrieved {len(anime_ids)} IDs for inserted records",
        )

        return anime_ids

    def _bulk_update_anime_records(
        self, session: Session, updates: List[Tuple[int, AnimeRecord]]
    ) -> None:
        """Update multiple anime records using PostgreSQL bulk operations."""
        if not updates:
            return

        # PostgreSQL can handle much larger batches
        BATCH_SIZE = 1000

        # Process updates in batches
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i : i + BATCH_SIZE]

            # Prepare update data with primary keys
            update_values = []
            for anime_id, record in batch:
                record_dict = asdict(record)
                record_dict["id"] = anime_id  # Include the primary key for bulk update
                # Remove None values and ensure all values are proper Python types
                clean_dict = {}
                for k, v in record_dict.items():
                    if v is not None:
                        # Ensure the value is a proper Python type, not a SQLAlchemy object
                        if hasattr(v, "__dict__") and not isinstance(
                            v, (str, int, float, bool, list, dict)
                        ):
                            # Skip complex objects that can't be serialized
                            continue
                        clean_dict[k] = v
                update_values.append(clean_dict)

            if update_values:
                # Use PostgreSQL-specific bulk update with VALUES clause
                stmt = update(Anime)
                session.execute(stmt, update_values)

            # Log progress for large batches
            if len(updates) > BATCH_SIZE:
                pprint.print(
                    Platform.SYSTEM,
                    Status.INFO,
                    f"Updated batch {i // BATCH_SIZE + 1}/{(len(updates) + BATCH_SIZE - 1) // BATCH_SIZE}",
                )

    def _bulk_delete_anime_records(
        self, session: Session, anime_ids: List[int]
    ) -> None:
        """Delete multiple anime records using PostgreSQL bulk operations."""
        if not anime_ids:
            return

        # PostgreSQL can handle much larger batches
        BATCH_SIZE = 1000

        # Process deletes in batches
        for i in range(0, len(anime_ids), BATCH_SIZE):
            batch = anime_ids[i : i + BATCH_SIZE]

            # Use bulk delete with IN clause
            stmt = delete(Anime).where(Anime.id.in_(batch))
            session.execute(stmt)

            # Log progress for large batches
            if len(anime_ids) > BATCH_SIZE:
                pprint.print(
                    Platform.SYSTEM,
                    Status.INFO,
                    f"Deleted batch {i // BATCH_SIZE + 1}/{(len(anime_ids) + BATCH_SIZE - 1) // BATCH_SIZE}",
                )

    def _bulk_log_changes(
        self, session: Session, anime_ids: List[int], change_type: str
    ) -> None:
        """Log multiple changes for KV sync."""
        if not anime_ids:
            return

        # PostgreSQL can handle larger batches for change logs
        BATCH_SIZE = 1000

        # Process logs in batches
        for i in range(0, len(anime_ids), BATCH_SIZE):
            batch = anime_ids[i : i + BATCH_SIZE]

            # Create change log entries
            change_logs = [
                {"anime_id": anime_id, "change_type": change_type} for anime_id in batch
            ]

            # Use SQLAlchemy 2.0 recommended approach for bulk insert
            stmt = insert(ChangeLog)
            session.execute(stmt, change_logs)

            # Log progress for large batches
            if len(anime_ids) > BATCH_SIZE:
                pprint.print(
                    Platform.SYSTEM,
                    Status.INFO,
                    f"Logged {change_type} changes batch {i // BATCH_SIZE + 1}/{(len(anime_ids) + BATCH_SIZE - 1) // BATCH_SIZE}",
                )

    def get_manual_mappings(self, platform: str) -> Dict[str, str]:
        """Get manual mappings for a platform."""
        with self.Session() as session:
            result = session.execute(
                select(ManualMapping.platform_id, ManualMapping.platform_slug).where(
                    ManualMapping.platform == platform
                )
            )
            mappings = result.all()

            return {
                mapping.platform_id: mapping.platform_slug or mapping.platform_id
                for mapping in mappings
            }

    def get_anime_count(self) -> int:
        """Get total count of anime records."""
        with self.Session() as session:
            result = session.execute(select(func.count(Anime.id)))
            count = result.scalar()
            return count or 0

    def get_pending_changes(self) -> List[ChangeLog]:
        """Get unprocessed change log entries."""
        with self.Session() as session:
            result = session.execute(
                select(ChangeLog)
                .where(ChangeLog.processed.is_(False))
                .order_by(ChangeLog.created_at)
            )
            changes = result.scalars().all()

            return list(changes)

    def get_all_anime_records(self) -> List[Anime]:
        """Get all anime records from the database."""
        with self.Session() as session:
            result = session.execute(select(Anime))
            records = result.scalars().all()
            return list(records)

    def mark_changes_processed(self, change_ids: List[int]) -> None:
        """Mark change log entries as processed."""
        if not change_ids:
            return

        # PostgreSQL can handle larger batches
        BATCH_SIZE = 1000

        with self.Session() as session:
            for i in range(0, len(change_ids), BATCH_SIZE):
                batch = change_ids[i : i + BATCH_SIZE]
                stmt = (
                    update(ChangeLog)
                    .where(ChangeLog.id.in_(batch))
                    .values(processed=True, processed_at=func.now())
                )
                session.execute(stmt)
            session.commit()

    def get_platform_count(self, platform: str) -> int:
        """Get count of non-null entries for a specific platform."""
        try:
            with self.Session() as session:
                # Get the column by name
                column = getattr(Anime, platform, None)
                if column is None:
                    return 0

                # Count non-null entries
                result = session.execute(
                    select(func.count(column)).filter(column.is_not(None))
                )
                count = result.scalar()
                return count or 0

        except Exception as e:
            pprint.print(
                Platform.SYSTEM, Status.WARN, f"Error counting {platform}: {e}"
            )
            return 0

    def close(self) -> None:
        """Close database connection."""
        self.engine.dispose()
