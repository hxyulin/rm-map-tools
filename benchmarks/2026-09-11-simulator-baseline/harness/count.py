import json,struct,hashlib
from pathlib import Path
root=Path('/Users/hxyulin/dev/RM/assets/rm2026-field')
rows=[]
for path in sorted(root.rglob('*.glb')):
    b=path.read_bytes();n=struct.unpack_from('<I',b,12)[0];g=json.loads(b[20:20+n]);a=g['accessors']
    def counts(m):
        ps=g['meshes'][m]['primitives'];return sum((a[p['indices']]['count'] if 'indices'in p else a[p['attributes']['POSITION']]['count'])//3 for p in ps if p.get('mode',4)==4)
    nodes=g.get('nodes',[])
    def visit(i):
        node=nodes[i];return (counts(node['mesh']) if 'mesh'in node else 0)+sum(visit(j) for j in node.get('children',[]))
    rows.append(dict(file=str(path.relative_to(root)),triangles_unique=sum(counts(i) for i in range(len(g.get('meshes',[])))),triangles_scene=sum(visit(i) for i in g['scenes'][g.get('scene',0)]['nodes']),meshes=len(g.get('meshes',[])),primitives=sum(len(m['primitives']) for m in g.get('meshes',[])),bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
print(json.dumps(rows,indent=2))
