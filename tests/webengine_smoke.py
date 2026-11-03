"""Run separately with QT_QPA_PLATFORM=offscreen; exercises real Qt WebEngine."""
import importlib
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import aqt  # Import Anki's QtWebEngine bindings before creating QApplication.
from aqt.qt import QApplication, QEventLoop, QTimer, QWebEngineView

root = Path(__file__).resolve().parents[1]
package = types.ModuleType("ada_web_smoke")
package.__path__ = [str(root)]
sys.modules[package.__name__] = package
integration = importlib.import_module("ada_web_smoke.statistics_integration")
app = QApplication([])
view = QWebEngineView()
loop = QEventLoop()
outcome = {}
query = '-deck:"Archive 日本語"'

def done(result):
    outcome.update(result or {})
    loop.quit()

def loaded(ok):
    if not ok:
        loop.quit()
        return
    view.page().runJavaScript(integration.search_script(query), lambda result:
        view.page().runJavaScript("({query: window.query, custom: window.custom, value: document.getElementById('statisticsSearchText').value})", done))

view.loadFinished.connect(loaded)
view.setHtml("""<input id='statisticsSearchText'><script>
let text = ''; window.query = ''; window.custom = false;
const el = document.getElementById('statisticsSearchText');
el.addEventListener('focus', () => window.custom = true);
el.addEventListener('input', () => text = el.value);
el.addEventListener('change', () => window.query = text);
</script>""")
QTimer.singleShot(15000, loop.quit)
loop.exec()
assert outcome == {"query": query, "custom": True, "value": query}, outcome
print("Qt WebEngine search-event smoke test passed")
view.close()
