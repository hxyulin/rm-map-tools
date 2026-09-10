# SPDX-License-Identifier: MIT OR Apache-2.0
"""Alternate local warm-cache package loads and app scene-ready measurements."""
import argparse,datetime,json,re,subprocess,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('simulator',type=Path);p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('output',type=Path)
p.add_argument('--runs',type=int,default=3)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
report={'scope':'Alternating local runs, OS caches not cleared. Scene-ready is CPU scene instantiation, not first presented frame. Screenshot exit includes fixed warmup frames.','runs':[]}
for run in range(a.runs):
    for name,root in [('before',a.before),('after',a.after)]:
        start=time.perf_counter()
        command=[str(a.simulator/'target/debug/examples/inspect_assets'),str(root.resolve())]
        r=subprocess.run(command,capture_output=True,text=True,check=True)
        wall=time.perf_counter()-start
        (a.output/f'{name}-{run}-inspect.log').write_text(r.stdout+r.stderr)
        record={'package':name,'run':run,'loader_wall_seconds':wall,
                'verification_seconds':float(re.search(r'verification: ([\d.]+)s',r.stdout)[1]),
                'terrain_parse_seconds':float(re.search(r'parsed in ([\d.]+)s',r.stdout)[1]),
                'collider_triangles':sum(int(n) for n in re.findall(r'(\d+) (?:ground|fixture|equipment) triangles',r.stdout))}
        command=[str(a.simulator/'target/debug/rm-simulator'),'--cad-assets',str(root.resolve()),'--fly','--start-paused','--spawn','4,-4,2.6','--spawn-yaw-deg','135','--screenshot',str((a.output/f'{name}-{run}.png').resolve())]
        start=time.perf_counter()
        r=subprocess.run(command,capture_output=True,text=True,check=True,timeout=120)
        record['app_exit_seconds']=time.perf_counter()-start
        log=r.stdout+r.stderr;(a.output/f'{name}-{run}-app.log').write_text(log)
        stamps=[];ready=[]
        for line in log.splitlines():
            m=re.search(r'(\d{4}-\d\d-\d\dT[\d:.]+Z)',line)
            if m:
                stamp=datetime.datetime.fromisoformat(m[1]);stamps.append(stamp)
                if 'instance ready' in line:ready.append(stamp)
        if not stamps or not ready:raise ValueError('missing scene-ready logs')
        record['scene_ready_seconds']=(max(ready)-min(stamps)).total_seconds()
        report['runs'].append(record)
        (a.output/'startup.json').write_text(json.dumps(report,indent=2)+'\n')
        print(name,run,record,flush=True)
