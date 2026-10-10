"""Local session diagnostics; no document payloads or remote transmission."""
from __future__ import annotations

import ctypes
import functools
import inspect
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import sys
import tempfile
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from importlib.metadata import version, PackageNotFoundError

log = logging.getLogger('pptx2web')
_lock = threading.RLock()
_handler = None
_pending = {}
_last_js = None


def initialize():
    global _handler
    with _lock:
        if _handler is not None:
            return Path(_handler.baseFilename).parent
        session = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        primary = Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'pptx2web' / 'logs'
        fallback = False
        for directory in (primary, Path(tempfile.gettempdir()) / 'pptx2web-diagnostics' / 'logs'):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(directory / f'session-{session}.log', maxBytes=5 * 1024 * 1024,
                                              backupCount=2, encoding='utf-8')
                break
            except OSError:
                fallback = True
        else:
            raise OSError('No se pudo crear la carpeta de diagnóstico')
        handler.setFormatter(logging.Formatter(
            f'%(asctime)s session={session} pid=%(process)d thread=%(threadName)s/%(thread)d %(levelname)s %(name)s %(message)s'))
        _handler = handler
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        logging.raiseExceptions = False
        sessions = sorted(directory.glob('session-*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in sessions[10:]:
            for candidate in (old, Path(str(old) + '.1'), Path(str(old) + '.2')):
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    log.warning('No se pudo eliminar log antiguo %s', candidate.name)
        from . import __version__
        try:
            webview_version = version('pywebview')
        except PackageNotFoundError:
            webview_version = 'unavailable'
        log.info('session.start app=%s python=%s pywebview=%s windows=%s frozen=%s logs=%s fallback=%s',
                 __version__, platform.python_version(), webview_version, platform.platform(),
                 bool(getattr(sys, 'frozen', False)), directory, fallback)
        sys.excepthook = lambda typ, value, tb: log.critical('Unhandled Python exception', exc_info=(typ, value, tb))
        threading.excepthook = lambda args: log.critical('Unhandled thread exception', exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        return directory


@contextmanager
def operation(name):
    token = uuid.uuid4().hex[:10]
    start = time.monotonic()
    with _lock:
        _pending[token] = (name, start)
    log.info('operation.start id=%s name=%s', token, name)
    try:
        yield
    except BaseException:
        log.exception('operation.error id=%s name=%s', token, name)
        raise
    finally:
        log.info('operation.end id=%s name=%s elapsed_ms=%.1f', token, name, (time.monotonic() - start) * 1000)
        with _lock:
            _pending.pop(token, None)


def timed(name):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            with operation(name):
                result = fn(*args, **kwargs)
                status = ('error' if result.get('ok') is False else 'ok') if isinstance(result, dict) else ('cancelled' if result is None and name.startswith('dialog.') else 'ok')
                log.info('operation.result name=%s status=%s', name, status)
                return result
        # pywebview uses getfullargspec, which otherwise sees only *args/**kwargs.
        wrapped.__signature__ = inspect.signature(fn)
        return wrapped
    return decorate


def selected_file(path):
    if path:
        p = Path(path)
        try:
            size = p.stat().st_size if p.is_file() else None
        except OSError:
            size = None
        log.info('selected name=%s bytes=%s', p.name, size)


def heartbeat():
    global _last_js
    _last_js = time.monotonic()


def native_probe(window):
    """IsHungAppWindow is non-blocking; never Invoke/evaluate JS from supervisor."""
    if sys.platform != 'win32':
        return None
    native = getattr(window, 'native', None)
    if native is None:
        return None
    handle = getattr(native, 'Handle', None)
    if handle is None:
        return None
    hwnd = handle.ToInt64() if hasattr(handle, 'ToInt64') else int(handle)
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.IsHungAppWindow.argtypes = [ctypes.c_void_p]
    user32.IsHungAppWindow.restype = ctypes.c_int
    return not bool(user32.IsHungAppWindow(hwnd))


class Supervisor:
    def __init__(self, probe, clock=time.monotonic):
        self.probe = probe
        self.clock = clock
        self.stop_event = threading.Event()
        self.unresponsive_since = None
        self.last_dump = float('-inf')
        self.hung = False
        self.dialog_dumped = set()

    def snapshot(self, reason, pending):
        log.warning('diagnostic.snapshot reason=%s pending=%s', reason, pending)
        names = {t.ident: t.name for t in threading.enumerate()}
        for ident, frame in sys._current_frames().items():
            log.warning('Python stack thread=%s/%s\n%s', names.get(ident, '?'), ident, ''.join(traceback.format_stack(frame)))

    def tick(self):
        now = self.clock()
        with _lock:
            pending = {key: (name, now - start) for key, (name, start) in _pending.items()}
        dialogs = {key for key, (name, age) in pending.items() if name.startswith('dialog.')}
        self.dialog_dumped.intersection_update(dialogs)
        native = self.probe()
        # A modal selector can suspend JS while remaining healthy natively.
        js_stale = _last_js is not None and now - _last_js >= 15 and not dialogs
        stalled = native is False or js_stale
        if stalled:
            if self.unresponsive_since is None:
                self.unresponsive_since = now - 15 if js_stale and native is not False else now
            if now - self.unresponsive_since >= 15 and now - self.last_dump >= 60:
                self.snapshot('native-unresponsive' if native is False else 'javascript-heartbeat-missing', pending)
                self.last_dump = now
                self.hung = True
        else:
            if self.hung:
                log.info('diagnostic.recovered')
            self.unresponsive_since = None
            self.hung = False
        slow = {key for key in dialogs if pending[key][1] >= 30} - self.dialog_dumped
        if slow and now - self.last_dump >= 60:
            self.snapshot('dialog-wait (may be user interaction)', pending)
            self.last_dump = now
            self.dialog_dumped.update(slow)

    def run(self):
        while not self.stop_event.wait(1):
            try:
                self.tick()
            except Exception:
                log.exception('Supervisor probe failed')
                self.stop_event.wait(30)

    def start(self):
        threading.Thread(target=self.run, name='diagnostics-supervisor', daemon=True).start()

    def stop(self):
        self.stop_event.set()
        log.info('session.end')


def main():
    initialize()
    from .gui.app import main as gui_main
    gui_main()


def read_session_logs(limit=256 * 1024):
    """Bounded tail of the current session including rotation backups."""
    initialize()
    handler = _handler
    handler.acquire()
    try:
        handler.flush()
        remaining = limit
        parts = []
        truncated = False
        for suffix in ("", ".1", ".2"):
            path = Path(handler.baseFilename + suffix)
            if not path.exists():
                continue
            size = path.stat().st_size
            take = min(size, remaining)
            if take:
                with path.open("rb") as stream:
                    stream.seek(size - take)
                    parts.insert(0, stream.read(take).decode("utf-8", errors="replace"))
            remaining -= take
            if take < size:
                truncated = True
        return {"ok": True, "session": Path(handler.baseFilename).stem,
                "text": "".join(parts), "truncated": truncated}
    except OSError:
        log.exception("Cannot read session logs")
        return {"ok": False, "error": "No se pudieron leer los logs. Abre la carpeta de diagnóstico."}
    finally:
        handler.release()
