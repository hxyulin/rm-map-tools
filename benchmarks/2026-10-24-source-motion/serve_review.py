"""Loopback-only review server; POST saves only named WebP captures in review/."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import re,json,argparse
ROOT=Path(__file__).resolve().parents[2]/'out/rmuc2027-source-motion/review'
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kw):super().__init__(*args,directory=str(ROOT),**kw)
 def do_POST(self):
  match=re.fullmatch(r'/capture/([a-z0-9-]+)',self.path)
  n=int(self.headers.get('Content-Length','0'))
  if not match or not 0<n<5_000_000:self.send_error(400);return
  payload=self.rfile.read(n)
  if payload[:4]!=b'RIFF' or payload[8:12]!=b'WEBP':self.send_error(400);return
  path=ROOT/(match[1]+'.webp');path.write_bytes(payload)
  body=json.dumps({'path':str(path),'bytes':len(payload)}).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8767);a=p.parse_args()
 print(f'Read-only model review: http://127.0.0.1:{a.port}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
