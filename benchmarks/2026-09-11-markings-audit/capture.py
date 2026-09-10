# SPDX-License-Identifier: MIT OR Apache-2.0
"""Capture reviewed artwork groups from audit.py's report without editing assets."""
import argparse
import html
import json
from pathlib import Path
import sys

import numpy as np
import vtk
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import read_glb, scene_nodes, accessor
from preview.render_joints import actor_for_primitive, vtk_matrix, label

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('report', type=Path)
args = parser.parse_args()
report = json.loads(args.report.read_text())
out = args.report.parent
window = vtk.vtkRenderWindow()
window.SetOffScreenRendering(1)
window.SetSize(1600, 1050)
for column, (group, count) in enumerate(report['groups'].items()):
    rows = [r for r in report['rows'] if r['group'] == group]
    if count['asset'] == 'rune':
        rows = rows[:1]
    if count['asset'] == 'centre-platform':
        rows = [r for r in rows if 3 <= r['node'] <= 13]
    d, b = read_glb(rows[0]['file'])
    matrices = {i:w for i,w,_ in scene_nodes(d)}
    ren = vtk.vtkRenderer()
    ren.SetViewport(column % 2 / 2, 1-(column//2+1)/3, (column%2+1)/2, 1-column//2/3)
    ren.SetBackground(.25, .28, .33)
    window.AddRenderer(ren)
    points = []
    for row in rows:
        pr = d['meshes'][d['nodes'][row['node']]['mesh']]['primitives'][row['primitive']]
        actor = actor_for_primitive(d,b,pr)
        matrix = matrices[row['node']]
        actor.SetUserMatrix(vtk_matrix(matrix))
        ren.AddActor(actor)
        p = accessor(d,b,pr['attributes']['POSITION'])
        points.append(p @ matrix[:3,:3].T + matrix[:3,3])
    p = np.vstack(points)
    center = (p.min(0)+p.max(0))/2
    q = p-p.mean(0)
    _, basis = np.linalg.eigh(q.T@q)
    direction, up = basis[:,0], basis[:,1]
    camera = ren.GetActiveCamera()
    camera.SetPosition(*(center+direction*max(np.ptp(p,axis=0))*3))
    camera.SetFocalPoint(*center)
    camera.SetViewUp(*up)
    camera.ParallelProjectionOn()
    ren.ResetCamera()
    camera.SetParallelScale(camera.GetParallelScale()*1.05)
    ren.ResetCameraClippingRange()
    title = group + (' | one side shown' if count['asset'] in ('rune', 'centre-platform') else '')
    label(ren, title, 12, 318, 20, (1,1,1))
    label(ren, f'{count["visual"]:,} placed visual triangles', 12, 12, 17, (1,1,1))
window.Render()
im = vtk.vtkWindowToImageFilter()
im.SetInput(window)
im.ReadFrontBufferOff()
im.Update()
writer = vtk.vtkPNGWriter()
writer.SetFileName(str(out/'artwork-overview.png'))
writer.SetInputConnection(im.GetOutputPort())
writer.Write()
window.Finalize()
parts = ['<!doctype html><meta charset="utf-8"><title>Text and markings audit</title>',
         '<style>body{font:16px system-ui;max-width:1400px;margin:32px auto;background:#eef1f5;color:#17212b}img{width:100%}td,th{padding:8px 18px;text-align:left}details{margin:20px 0}a{color:#2465a0}</style>',
         '<h1>Text and markings audit</h1><p>Current deployed package. Counts include arena placements. These are reviewed candidates, not a complete classification of artwork embedded inside mixed mechanical meshes.</p>',
         '<img src="artwork-overview.png"><table><tr><th>Selection</th><th>Visual triangles</th><th>Collider-file triangles</th></tr>']
for group, g in report['groups'].items():
    parts.append(f'<tr><td>{html.escape(group)}</td><td>{g["visual"]:,}</td><td>{g["collision_file"]:,}</td></tr>')
parts.append('</table><p>Collider counts describe matching geometry in files, not actual physics contacts. Rune artwork is separate from its backing disks and controlled light surfaces. No assets changed.</p><h2>Full inventory captures</h2><p>Every one of the 1,083 scene mesh sections is captured below. Small sections have fewer than 100 triangles. Labels give node and primitive indices; cameras fit each section independently. Geometry mixed into a large assembly can still be occluded or too small to identify.</p>')
for asset in report['assets']:
    paths = sorted(out.glob(asset+'-*.png'))
    if paths:
        parts.append(f'<details><summary>{html.escape(asset)}: {len(paths)} contact sheets</summary>')
        for p in paths:
            parts.append(f'<h3>{html.escape(p.stem)}</h3><a href="{p.name}"><img loading="lazy" src="{p.name}"></a>')
        parts.append('</details>')
parts.append('<p><a href="report.json">Full counts, selectors, bounds and checksums</a></p>')
(out/'index.html').write_text('\n'.join(parts))
