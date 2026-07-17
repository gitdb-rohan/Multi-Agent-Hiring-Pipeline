"""
Directory watcher for continuous resume ingestion.
Monitors a folder for new or modified resume files (PDF/DOCX) and automatically
ingests them into the vector store and database.

Run as a standalone process:
    uv run python -m app.ingestion.watcher

Or import and start programmatically.
"""
import os
import time
import shutil
import asyncio
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from app.config import settings
from app.ingestion.resume_parser import extract_text_from_file, is_supported_resume
from app.ingestion.profile_extractor import extract_profile_from_resume
from app.infra.vector_store import vector_store

logger = logging.getLogger(__name__)


class ResumeEventHandler(FileSystemEventHandler):
    """Handles file system events for new/modified resume files."""

    def __init__(self, processed_dir: str):
        super().__init__()
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        # Track files being processed to avoid duplicate events
        self._processing: set[str] = set()

    def on_created(self, event):
        if not event.is_directory and is_supported_resume(event.src_path):
            self._handle_resume(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and is_supported_resume(event.src_path):
            self._handle_resume(event.src_path)

    def _handle_resume(self, file_path: str):
        """Process a resume file — runs async extraction in a new event loop."""
        if file_path in self._processing:
            return
        self._processing.add(file_path)

        try:
            # Small delay to ensure file write is complete
            time.sleep(0.5)
            logger.info(f"New resume detected: {file_path}")
            
            # Run the async ingestion in a new event loop
            # (watchdog callbacks run in a separate thread)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._ingest_resume(file_path))
            finally:
                loop.close()
            
            # Move processed file to processed directory
            dest = self.processed_dir / Path(file_path).name
            shutil.move(file_path, str(dest))
            logger.info(f"Processed and moved to: {dest}")

        except Exception as e:
            logger.error(f"Failed to process resume {file_path}: {e}")
        finally:
            self._processing.discard(file_path)

    async def _ingest_resume(self, file_path: str):
        """Extract text, build profile, upsert to vector store."""
        # 1. Parse resume text
        raw_text = extract_text_from_file(file_path)
        if not raw_text.strip():
            logger.warning(f"Empty text from {file_path}, skipping")
            return

        # 2. Extract structured profile via LLM
        profile = await extract_profile_from_resume(raw_text)

        # 3. Upsert to ChromaDB (dedup handled by deterministic ID)
        vector_store.upsert_candidate(
            candidate_id=profile.id,
            document=profile.to_embedding_text(),
            metadata=profile.to_chroma_metadata(),
        )
        logger.info(f"Ingested candidate: {profile.name} (ID: {profile.id})")


class ResumeDirectoryWatcher:
    """
    Watches a directory for new/modified resume files and auto-ingests them.
    
    Usage:
        watcher = ResumeDirectoryWatcher("/path/to/resumes")
        watcher.start()  # non-blocking
        # ... later ...
        watcher.stop()
    """

    def __init__(self, watch_dir: str | None = None, processed_dir: str | None = None):
        self.watch_dir = Path(watch_dir or settings.RESUME_WATCH_DIR)
        self.processed_dir = Path(processed_dir or settings.RESUME_PROCESSED_DIR)
        self.observer = Observer()
        
        # Ensure directories exist
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def start(self):
        """Start watching the directory (non-blocking)."""
        handler = ResumeEventHandler(str(self.processed_dir))
        self.observer.schedule(handler, str(self.watch_dir), recursive=False)
        self.observer.start()
        logger.info(f"Resume watcher started — watching: {self.watch_dir}")
        logger.info(f"Processed files will be moved to: {self.processed_dir}")

    def stop(self):
        """Stop the watcher."""
        self.observer.stop()
        self.observer.join()
        logger.info("Resume watcher stopped.")

    def process_existing(self):
        """Process all existing resume files in the watch directory (one-time batch)."""
        import asyncio
        
        files = [
            str(f) for f in self.watch_dir.iterdir()
            if f.is_file() and is_supported_resume(str(f))
        ]
        
        if not files:
            logger.info(f"No resume files found in {self.watch_dir}")
            return
        
        logger.info(f"Processing {len(files)} existing resume files...")
        handler = ResumeEventHandler(str(self.processed_dir))
        for file_path in files:
            handler._handle_resume(file_path)


# CLI entrypoint: uv run python -m app.ingestion.watcher
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    
    watcher = ResumeDirectoryWatcher()
    
    # First, process any existing files
    watcher.process_existing()
    
    # Then watch for new files
    print(f"\nWatching for new resumes in: {watcher.watch_dir}")
    print("Drop PDF or DOCX files into this directory to auto-ingest them.")
    print("Press Ctrl+C to stop.\n")
    
    watcher.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("\nWatcher stopped.")
