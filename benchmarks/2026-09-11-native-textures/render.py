"""Load self-contained GLBs through VTK's glTF importer and render fixed views."""
import json
from pathlib import Path
import numpy as np
import vtk
from gltf_scene import read_glb, scene_nodes

root=Path('out/native-texture-candidate')
doc,_=read_glb(root/'equipment/base.glb')
patch=json.loads((root/'equipment/texture-atlas.json').read_text())['files']['base.glb']['patches'][0]
ni=next(i for i,n in enumerate(doc['nodes']) if n.get('name')==patch['node'])
world={i:w for i,w,_ in scene_nodes(doc)}[ni]
corners=np.asarray(patch['corners_node_m'])@world[:3,:3].T+world[:3,3]
center=corners.mean(0)
normal=np.cross(corners[1]-corners[0],corners[3]-corners[0]);normal/=np.linalg.norm(normal)
up=corners[3]-corners[0];up/=np.linalg.norm(up)
for name,path in [('before',Path('../rm-simulator/local-assets/field/equipment/base.glb')),('after',root/'equipment/base.glb')]:
 window=vtk.vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(1100,800)
 importer=vtk.vtkGLTFImporter();importer.SetFileName(str(path.resolve()));importer.SetRenderWindow(window);importer.Update()
 ren=importer.GetRenderer();ren.SetBackground(.18,.20,.23)
 camera=ren.GetActiveCamera();camera.SetPosition(*(center+normal*1));camera.SetFocalPoint(*center);camera.SetViewUp(*(-up))
 camera.ParallelProjectionOn();camera.SetParallelScale(.17);ren.ResetCameraClippingRange()
 window.Render()
 capture=vtk.vtkWindowToImageFilter();capture.SetInput(window);capture.ReadFrontBufferOff();capture.Update()
 writer=vtk.vtkPNGWriter();writer.SetFileName(str(root/f'base-{name}.png'));writer.SetInputConnection(capture.GetOutputPort());writer.Write();window.Finalize()
# Arena overview, with identical cameras for both exports.
from gltf_scene import mesh_instances
original,bin=read_glb(Path('../rm-simulator/local-assets/field/arena-static.glb'))
points=np.vstack([p for _,_,p,_,_ in mesh_instances(original,bin)])
lo,hi=points.min(0),points.max(0);center=(lo+hi)/2
for name,path in [('before',Path('../rm-simulator/local-assets/field/arena-static.glb')),('after',root/'arena-static.glb')]:
 window=vtk.vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(1400,1100)
 importer=vtk.vtkGLTFImporter();importer.SetFileName(str(path.resolve()));importer.SetRenderWindow(window);importer.Update()
 ren=importer.GetRenderer();ren.SetBackground(.18,.20,.23)
 camera=ren.GetActiveCamera();camera.SetPosition(*(center+np.array([0,0,100])));camera.SetFocalPoint(*center);camera.SetViewUp(0,1,0)
 camera.ParallelProjectionOn();camera.SetParallelScale(max((hi-lo)[1],(hi-lo)[0]*1100/1400)*.53);ren.ResetCameraClippingRange()
 window.Render()
 capture=vtk.vtkWindowToImageFilter();capture.SetInput(window);capture.ReadFrontBufferOff();capture.Update()
 writer=vtk.vtkPNGWriter();writer.SetFileName(str(root/f'arena-{name}.png'));writer.SetInputConnection(capture.GetOutputPort());writer.Write();window.Finalize()
