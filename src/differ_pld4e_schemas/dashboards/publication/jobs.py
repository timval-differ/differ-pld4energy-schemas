"""
Exports that run in a background thread, so a large upload does not hold up
the requests of other users.

Each export is a folder with its state (`job.json`) and, when done, the ZIP.
The state is kept on disk, not in memory, because NOMAD may run several API
processes: the request that asks for the state of an export can reach another
process than the one that started it. For the same reason a process cannot
tell whether an export of another process still runs: an export that has run
for longer than `STUCK_AFTER` counts as interrupted (e.g. by a restart of
NOMAD). Exports older than `LIFETIME` are deleted when the next one starts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from differ_pld4e_schemas.snapshot import SnapshotError

logger = logging.getLogger(__name__)

LIFETIME = 24 * 60 * 60  # seconds
STUCK_AFTER = 2 * 60 * 60  # seconds
# Exports at the same time, per NOMAD process; more wait for their turn.
MAX_RUNNING = 2

INTERRUPTED = (
    'The export was interrupted, probably by a restart of NOMAD. Export again.'
)
UNEXPECTED = 'The export failed unexpectedly. Ask a maintainer to check the NOMAD log.'

_ID = re.compile(r'[0-9a-f]{32}')

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _default_executor() -> ThreadPoolExecutor:
    """Made on first use, not on import: after any fork of the NOMAD server."""
    global _executor  # noqa: PLW0603
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                MAX_RUNNING, thread_name_prefix='publication-export'
            )
        return _executor


class AlreadyRunning(Exception):
    """The user has an export running; one at a time."""


class Jobs:
    def __init__(self, directory: Path, executor=None):
        self.directory = Path(directory)
        self._executor = executor

    @property
    def executor(self):
        return self._executor or _default_executor()

    def _folder(self, job_id: str) -> Path:
        if not _ID.fullmatch(job_id):
            raise KeyError(job_id)
        return self.directory / job_id

    def _write(self, job_id: str, state: dict) -> None:
        path = self._folder(job_id) / 'job.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        os.replace(temporary, path)  # never half written for a reader

    def _read(self, folder: Path) -> dict | None:
        try:
            state = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            state['status'] == 'running'
            and time.time() - state['started'] > STUCK_AFTER
        ):
            return {**state, 'status': 'failed', 'error': INTERRUPTED}
        return state

    def get(self, job_id: str, user_id: str) -> dict:
        """The state of an export of `user_id`; KeyError for any other."""
        state = self._read(self._folder(job_id))
        if state is None or state['user_id'] != user_id:
            raise KeyError(job_id)
        public = {key: value for key, value in state.items() if key != 'user_id'}
        return {'job_id': job_id, **public}

    def zip_path(self, job_id: str, user_id: str) -> Path:
        state = self.get(job_id, user_id)
        path = self._folder(job_id) / state.get('file_name', '')
        if state['status'] != 'done' or not path.is_file():
            raise KeyError(job_id)
        return path

    def _all(self):
        try:
            folders = list(self.directory.iterdir())
        except FileNotFoundError:
            return
        for folder in folders:
            if _ID.fullmatch(folder.name):
                state = self._read(folder)
                if state is not None:
                    yield folder, state

    def remove_expired(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        for folder, state in self._all():
            if now - state['started'] > LIFETIME:
                # Another NOMAD process may remove it at the same time.
                shutil.rmtree(folder, ignore_errors=True)

    def start(
        self,
        user_id: str,
        upload_id: str,
        build: Callable[[], dict[str, bytes]],
    ) -> dict:
        """Run `build` (the files of the export) in the background."""
        self.remove_expired()
        if any(
            state['user_id'] == user_id and state['status'] == 'running'
            for _, state in self._all()
        ):
            raise AlreadyRunning(user_id)
        job_id = uuid.uuid4().hex
        self._folder(job_id).mkdir(parents=True)
        state = {
            'user_id': user_id,
            'upload_id': upload_id,
            'status': 'running',
            'started': time.time(),
        }
        self._write(job_id, state)
        self.executor.submit(self._run, job_id, state, build)
        return self.get(job_id, user_id)

    def _run(self, job_id: str, state: dict, build) -> None:
        try:
            try:
                files = build()
                file_name = f'{state["upload_id"]}-publication.zip'
                with zipfile.ZipFile(
                    self._folder(job_id) / file_name, 'w', zipfile.ZIP_DEFLATED
                ) as archive:
                    for path in sorted(files):
                        archive.writestr(path, files.pop(path))
                result = {'status': 'done', 'file_name': file_name}
            except SnapshotError as error:
                result = {'status': 'failed', 'error': str(error)}
            except Exception:
                # A bug, or NOMAD failing: logged in full, the user told in short.
                logger.exception(
                    'Export %s of upload %s failed', job_id, state['upload_id']
                )
                result = {'status': 'failed', 'error': UNEXPECTED}
            self._write(job_id, {**state, **result})
        except Exception:
            # Nobody reads the future of this thread: log it, or it is lost.
            logger.exception('Export %s: its state could not be saved', job_id)
