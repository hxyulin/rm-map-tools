# SPDX-License-Identifier: MIT OR Apache-2.0
"""Render two Z-up element GLBs with the same orthographic camera."""
import argparse
from pathlib import Path
import sys
import numpy as np
import vtk
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import read_glb, scene_nodes
from preview.render_joints import actor_for_primitive, vtk_matrix, label

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('before', type=Path)
parser.add_argument('after', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--before-label', default='Simulation preset')
parser.add_argument('--after-label', default='Relaxed angular detail')
args = parser.parse_args()
window = vtk.vtkRenderWindow()
window.SetOffScreenRendering(1)
window.SetSize(1600, 900)
renderers = []
all_bounds = []
for column, (path, title) in enumerate([(args.before, args.before_label), (args.after, args.after_label)]):
    document, binary = read_glb(path)
    renderer = vtk.vtkRenderer()
    renderer.SetViewport(column / 2, 0, (column + 1) / 2, 1)
    renderer.SetBackground(.91, .93, .96)
    window.AddRenderer(renderer)
    total = 0
    for i, matrix, _ in scene_nodes(document):
        node = document['nodes'][i]
        if 'mesh' not in node: continue
        for primitive in document['meshes'][node['mesh']]['primitives']:
            actor = actor_for_primitive(document, binary, primitive)
            actor.SetUserMatrix(vtk_matrix(matrix))
            renderer.AddActor(actor)
            all_bounds.append(actor.GetBounds())
            total += document['accessors'][primitive['indices']]['count'] // 3
    label(renderer, title, 24, 850, 26, (.12, .16, .2))
    label(renderer, f'{total:,} triangles', 24, 815, 20, (.25, .3, .35))
    renderers.append(renderer)
lo = np.min([[b[0], b[2], b[4]] for b in all_bounds], axis=0)
hi = np.max([[b[1], b[3], b[5]] for b in all_bounds], axis=0)
center = (lo + hi) / 2
direction = np.array([-1.6, -1.2, .8])
for renderer in renderers:
    camera = renderer.GetActiveCamera()
    camera.SetPosition(*(center + direction * max(hi - lo) * 2.4))
    camera.SetFocalPoint(*center)
    camera.SetViewUp(0, 0, 1)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(max(hi - lo) * .8)
    renderer.ResetCameraClippingRange()
window.Render()
image = vtk.vtkWindowToImageFilter()
image.SetInput(window)
image.ReadFrontBufferOff()
image.Update()
args.output.parent.mkdir(parents=True, exist_ok=True)
writer = vtk.vtkPNGWriter()
writer.SetFileName(str(args.output))
writer.SetInputConnection(image.GetOutputPort())
writer.Write()
window.Finalize()
