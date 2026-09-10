# SPDX-License-Identifier: MIT OR Apache-2.0
import sys,json,math,argparse
from pathlib import Path
import numpy as np
import vtk
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from gltf_scene import read_glb,accessor
from preview.render_joints import actor_for_primitive,label
parser=argparse.ArgumentParser(description='Capture every section from an audit report.')
parser.add_argument('report',type=Path)
parser.add_argument('--small',action='store_true')
args=parser.parse_args()
rows=json.loads(args.report.read_text())['rows']
for asset in sorted(set(r['asset'] for r in rows)):
 rr=[r for r in rows if r['asset']==asset and (r['triangles']<100 if args.small else r['triangles']>=100)]
 if not rr:continue
 d,b=read_glb(rr[0]['file'])
 for page in range(math.ceil(len(rr)/24)):
  batch=rr[page*24:(page+1)*24];w=vtk.vtkRenderWindow();w.SetOffScreenRendering(1);w.SetSize(1600,1200)
  for j,r in enumerate(batch):
   ren=vtk.vtkRenderer();ren.SetViewport(j%4/4,1-(j//4+1)/6,(j%4+1)/4,1-j//4/6);ren.SetBackground(.92,.94,.97);w.AddRenderer(ren)
   pr=d['meshes'][d['nodes'][r['node']]['mesh']]['primitives'][r['primitive']];actor=actor_for_primitive(d,b,pr);ren.AddActor(actor)
   p=accessor(d,b,pr['attributes']['POSITION']).astype(float);c=(p.min(0)+p.max(0))/2;q=p-p.mean(0);ev,v=np.linalg.eigh(q.T@q);span=np.ptp(q@v,axis=0)
   direction=v[:,0] if span[0]<.005 else np.array([-1.6,-1.2,.8]);up=v[:,1] if span[0]<.005 else np.array([0,0,1]);cam=ren.GetActiveCamera();cam.SetPosition(*(c+direction*max(np.ptp(p,axis=0))*3));cam.SetFocalPoint(*c);cam.SetViewUp(*up);cam.ParallelProjectionOn();ren.ResetCamera();cam.SetParallelScale(cam.GetParallelScale()*1.12);ren.ResetCameraClippingRange();label(ren,f'n{r["node"]} p{r["primitive"]} | {r["triangles"]:,} tris',8,8,15,(.1,.1,.1))
  w.Render();im=vtk.vtkWindowToImageFilter();im.SetInput(w);im.ReadFrontBufferOff();im.Update();wr=vtk.vtkPNGWriter();wr.SetFileName(str(args.report.parent / f'{asset}-{"small-" if args.small else ""}{page}.png'));wr.SetInputConnection(im.GetOutputPort());wr.Write();w.Finalize()
 print(asset,len(rr),flush=True)
