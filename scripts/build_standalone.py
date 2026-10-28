#!/usr/bin/env python3
"""Build a self-contained static preview; accounts still require the Python API."""
import base64
import json
import mimetypes
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / 'index.html').read_text()

def inline_assets(text):
    def replace(match):
        path = ROOT / match.group(0)[2:]
        if not path.is_file():
            raise FileNotFoundError(path)
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        return 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode()
    return re.sub(r'\./assets/[A-Za-z0-9._-]+', replace, text)

html = re.sub(r'<link rel="stylesheet" href="\./([A-Za-z0-9._/-]+)">',
              lambda m: '<style>\n' + inline_assets((ROOT / m.group(1)).read_text()) + '\n</style>', html)
scripts = re.findall(r'<script src="\./([A-Za-z0-9._/-]+)" defer></script>', html)
html = re.sub(r'\s*<script src="\./[A-Za-z0-9._/-]+" defer></script>', '', html)
source = '\n'.join(inline_assets((ROOT / name).read_text()) for name in scripts)
# Escape the HTML raw-text closing sequence without changing JS values.
source = source.replace('</script', '<\\/script')
data = json.loads((ROOT / 'data/conferences.json').read_text())
embedded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
html = inline_assets(html).replace('</body>',
    '<script type="application/json" id="conference-data">' + embedded + '</script>\n<script>\n' + source + '\n</script>\n</body>')
(ROOT / 'dist').mkdir(exist_ok=True)
target = ROOT / 'dist/index.html'
target.write_text(html)
print(f'Standalone: dist/index.html ({target.stat().st_size:,} bytes)')
