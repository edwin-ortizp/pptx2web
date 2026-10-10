"""Diagnostics tests do not require PowerPoint or a native window."""
import logging
from pathlib import Path
import pytest
from pptx2web import diagnostics as d


@pytest.fixture
def session(tmp_path, monkeypatch):
    previous = d._handler
    old_level = logging.getLogger().level
    import sys, threading
    old_sys, old_thread = sys.excepthook, threading.excepthook
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(d, '_handler', None)
    monkeypatch.setattr(d, '_pending', {})
    monkeypatch.setattr(d, '_last_js', None)
    yield tmp_path
    if d._handler:
        logging.getLogger().removeHandler(d._handler)
        d._handler.close()
    d._handler = previous
    logging.getLogger().setLevel(old_level)
    sys.excepthook, threading.excepthook = old_sys, old_thread


def test_session_rotation_retention_and_idempotence(session):
    folder = session / 'pptx2web' / 'logs'
    folder.mkdir(parents=True)
    for i in range(12):
        (folder / f'session-old-{i}.log').write_text('old')
    assert d.initialize() == d.initialize()
    assert len(list(folder.glob('session-*.log'))) == 10
    handler = d._handler
    assert handler.maxBytes == 5 * 1024 * 1024
    assert handler.backupCount == 2
    handler.maxBytes = 600
    for i in range(30):
        d.log.info('rotation %s %s', i, 'á' * 100)
    assert Path(handler.baseFilename + '.1').exists()
    assert Path(handler.baseFilename + '.2').exists()
    assert not Path(handler.baseFilename + '.3').exists()


def test_fallback(session, monkeypatch):
    blocker = session / 'file'
    blocker.write_text('blocked')
    monkeypatch.setenv('LOCALAPPDATA', str(blocker))
    monkeypatch.setattr(d.tempfile, 'gettempdir', lambda: str(session / 'temp'))
    assert d.initialize() == session / 'temp' / 'pptx2web-diagnostics' / 'logs'
    assert 'fallback=True' in Path(d._handler.baseFilename).read_text(encoding='utf-8')


def test_operation_results_and_exception(session):
    d.initialize()
    @d.timed('dialog.test')
    def cancel():
        return None
    cancel()
    with pytest.raises(ValueError):
        with d.operation('failing'):
            raise ValueError('test failure')
    assert not d._pending
    content = Path(d._handler.baseFilename).read_text(encoding='utf-8')
    assert 'status=cancelled' in content
    assert 'elapsed_ms=' in content
    assert 'Traceback' in content and 'test failure' in content


def test_watchdog_recovery_rate_limit_and_dialog(session, monkeypatch):
    now = [0.0]
    alive = [False]
    watchdog = d.Supervisor(lambda: alive[0], clock=lambda: now[0])
    captures = []
    monkeypatch.setattr(watchdog, 'snapshot', lambda reason, pending: captures.append((reason, pending)))
    watchdog.tick()
    now[0] = 15
    watchdog.tick()
    now[0] = 20
    watchdog.tick()
    assert len(captures) == 1
    now[0] = 75
    watchdog.tick()
    assert len(captures) == 2
    alive[0] = True
    watchdog.tick()
    assert not watchdog.hung
    d._pending['dialog'] = ('dialog.pptx', 75)
    now[0] = 140
    d._last_js = 1
    watchdog.tick()
    assert captures[-1][0].startswith('dialog-wait')
    watchdog.tick()
    assert len(captures) == 3


def test_snapshot_includes_threads(session):
    d.initialize()
    d.Supervisor(lambda: True).snapshot('test', {})
    assert 'Python stack thread=' in Path(d._handler.baseFilename).read_text(encoding='utf-8')


def test_gui_selectors_and_load_failure(session, monkeypatch):
    d.initialize()
    from pptx2web.gui.app import Api
    api = Api()
    class Window:
        result = None
        def create_file_dialog(self, *args, **kwargs):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result
    window = Window()
    api._window = window
    for picker in (api.pick_pptx, api.pick_logo, api.pick_output_dir):
        assert picker() is None
        window.result = ('example.pptx',)
        assert picker() == 'example.pptx'
        window.result = RuntimeError('dialog failed')
        with pytest.raises(RuntimeError):
            picker()
        window.result = None
    result = api.load_deck(str(session / 'missing.pptx'))
    assert result['ok'] is False
    assert not d._pending
    content = Path(d._handler.baseFilename).read_text(encoding='utf-8')
    assert 'name=dialog.pptx' in content
    assert 'name=dialog.logo' in content
    assert 'name=dialog.folder' in content
    assert 'status=error' in content
    assert 'dialog failed' in content


def test_javascript_stall_even_if_native_alive(session, monkeypatch):
    now = [20.0]
    d._last_js = 0.0
    watchdog = d.Supervisor(lambda: True, clock=lambda: now[0])
    reasons = []
    monkeypatch.setattr(watchdog, 'snapshot', lambda reason, pending: reasons.append(reason))
    watchdog.tick()
    assert reasons == ['javascript-heartbeat-missing']


def test_bridge_signature_is_preserved():
    import inspect
    @d.timed('example')
    def exposed(self, path: str, flag=False):
        return path
    assert inspect.getfullargspec(exposed).args == ['self', 'path', 'flag']


def test_read_session_logs_rotation_tail_and_literal_text(session):
    d.initialize()
    handler = d._handler
    d.log.info('mensaje español <script>literal</script>')
    result = d.read_session_logs()
    assert result['ok'] and not result['truncated']
    assert 'mensaje español <script>literal</script>' in result['text']
    handler.doRollover()
    d.log.info('newest entry')
    result = d.read_session_logs()
    assert result['text'].index('mensaje español') < result['text'].index('newest entry')
    result = d.read_session_logs(limit=80)
    assert result['truncated']
    assert len(result['text'].encode('utf-8')) <= 84
    assert 'newest entry' in result['text']


def test_native_window_is_not_public_in_bridge(session):
    d.initialize()
    from pptx2web.gui.app import Api
    api = Api()
    api._window = object()
    assert "window" not in [name for name in dir(api) if not name.startswith("_")]


def test_conversion_snapshot_and_busy_requests(session, monkeypatch):
    import json
    from types import SimpleNamespace
    from pptx2web.gui import app
    api = app.Api()
    original = session / 'original.pptx'
    api._deck_path = original
    scheduled = []
    class DeferredThread:
        def __init__(self, target, args, **kwargs):
            scheduled.append((target, args))
        def start(self):
            pass
    monkeypatch.setattr(app.threading, 'Thread', DeferredThread)
    opts = {'config': {'course': {'title': 'original'}}, 'scale': 2}
    assert api.convert(opts) == {'started': True}
    assert api.convert(opts)['ok'] is False
    assert api.load_deck('other.pptx')['ok'] is False
    with pytest.raises(RuntimeError, match='curso'):
        api.pick_pptx()
    opts['config']['course']['title'] = 'modified'
    api._deck_path = session / 'other.pptx'  # even unexpected internal mutation must not redirect save
    received = []
    def fake_convert(**kwargs):
        received.append(kwargs)
        return SimpleNamespace(out_dir=session, index_path=session / 'index.html', slide_count=20,
                               image_bytes=1, media_count=0, build_id='test', warnings=[])
    monkeypatch.setattr(app.pipeline, 'convert', fake_convert)
    events = []
    monkeypatch.setattr(api, '_emit', lambda event, payload: events.append(event))
    target, args = scheduled[0]
    assert target(*args) == {'ok': True}
    assert received[0]['pptx_path'] == original
    assert received[0]['deck_config']['course']['title'] == 'original'
    assert json.loads((session / 'original.config.json').read_text())['course']['title'] == 'original'
    assert not (session / 'other.config.json').exists()
    assert events == ['done']
    assert not api._operation_lock.locked()


@pytest.mark.parametrize('failure', ['validation', 'powerpoint', 'render', 'encoding', 'save'])
def test_conversion_failure_reports_error_and_unlocks(session, monkeypatch, failure):
    from pptx2web.gui import app
    from types import SimpleNamespace
    d.initialize()
    api = app.Api()
    api._operation_lock.acquire()
    errors = {'validation': app.ValidationError, 'powerpoint': app.PowerPointNotAvailableError,
              'render': app.RenderError, 'encoding': OSError, 'save': OSError}
    def fail(*args, **kwargs):
        raise errors[failure]('injected ' + failure)
    if failure == 'save':
        monkeypatch.setattr(app.pipeline, 'convert', lambda **kwargs: SimpleNamespace())
        monkeypatch.setattr(api, '_save_config_for', fail)
    else:
        monkeypatch.setattr(app.pipeline, 'convert', fail)
    events = []
    monkeypatch.setattr(api, '_emit', lambda event, payload: events.append(event))
    assert api._convert_worker(session / 'input.pptx', {}) == {'ok': False}
    assert events == ['error']
    assert not api._operation_lock.locked()
    content = Path(d._handler.baseFilename).read_text(encoding='utf-8')
    assert 'name=conversion status=error' in content
    assert 'name=conversion status=ok' not in content
    assert 'Traceback' in content and 'injected ' + failure in content


def test_loading_releases_lock_on_unexpected_failure(session, monkeypatch):
    from pptx2web.gui import app
    api = app.Api()
    monkeypatch.setattr(api, '_load_deck', lambda path: (_ for _ in ()).throw(RuntimeError('load failed')))
    with pytest.raises(RuntimeError):
        api.load_deck('input.pptx')
    assert not api._operation_lock.locked()


def test_simultaneous_conversion_requests(session, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from pptx2web.gui import app
    api = app.Api()
    api._deck_path = session / 'input.pptx'
    entered, release = threading.Event(), threading.Event()
    def wait_worker(path, opts):
        entered.set()
        release.wait(5)
        api._operation_lock.release()
    monkeypatch.setattr(api, '_convert_worker', wait_worker)
    barrier = threading.Barrier(2)
    def request():
        barrier.wait(timeout=5)
        return api.convert({})
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(request) for _ in range(2)]
            results = [future.result(timeout=5) for future in futures]
        assert sum(result.get('started', False) for result in results) == 1
        assert entered.wait(5)
        assert api.load_deck('other.pptx')['ok'] is False
    finally:
        release.set()


def test_conversion_start_failure_releases_lock(session, monkeypatch):
    from pptx2web.gui import app
    api = app.Api()
    api._deck_path = session / 'input.pptx'
    class FailedThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            raise RuntimeError('thread start failed')
    monkeypatch.setattr(app.threading, 'Thread', FailedThread)
    with pytest.raises(RuntimeError, match='start failed'):
        api.convert({})
    assert not api._operation_lock.locked()


def test_no_deck_conversion_releases_lock(session):
    from pptx2web.gui import app
    api = app.Api()
    assert api.convert({})['ok'] is False
    assert not api._operation_lock.locked()
