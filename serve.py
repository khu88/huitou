#!/usr/bin/env python3
"""Run the app and its local account backend without installing packages."""
import argparse
from pathlib import Path
from server import make_server

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=8765)
parser.add_argument('--database', '--db', type=Path, help='SQLite path; defaults to .local/app.sqlite3')
args = parser.parse_args()
root = Path(__file__).resolve().parent
server = make_server(root, args.database, args.port)
print(f'会投 Local: http://127.0.0.1:{server.server_port}', flush=True)
print('账号数据保存在本机 SQLite；本地私有扩展不会随公开版本分发。', flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()
