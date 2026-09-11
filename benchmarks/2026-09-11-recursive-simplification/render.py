# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fixed-camera native glTF comparisons, including embedded artwork."""
from pathlib import Path
import sys
import numpy as np
import vtk
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import read_glb, mesh_instances

for name in ('resource-zone', 'base'):
    root = Path('out/recursive-simplification') / name
    d, b = read_glb(root / 'current.glb')
    points = np.concatenate([p for _, _, p, _, _ in mesh_instances(d, b)])
    lo, hi = points.min(0), points.max(0)
    center = (lo + hi) / 2
    images = []
    for filename, title in [('current', 'Current'), ('guarded-3', 'Repeated, 12 mm source limit'), ('guarded-18mm-3', 'Repeated, 18 mm source limit')]:
        window = vtk.vtkRenderWindow(); window.SetOffScreenRendering(1); window.SetSize(900, 900)
        importer = vtk.vtkGLTFImporter(); importer.SetFileName(str((root / (filename + '.glb')).resolve())); importer.SetRenderWindow(window); importer.Update()
        renderer = importer.GetRenderer(); renderer.SetBackground(.86, .89, .93)
        camera = renderer.GetActiveCamera(); camera.SetPosition(*(center + np.array([-1.6, -1.2, .8])*max(hi-lo)*2.4)); camera.SetFocalPoint(*center); camera.SetViewUp(0, 0, 1); camera.ParallelProjectionOn(); camera.SetParallelScale(max(hi-lo)*.66); renderer.ResetCameraClippingRange()
        window.Render(); capture = vtk.vtkWindowToImageFilter(); capture.SetInput(window); capture.ReadFrontBufferOff(); capture.Update()
        path = root / (filename + '.png'); writer = vtk.vtkPNGWriter(); writer.SetFileName(str(path)); writer.SetInputConnection(capture.GetOutputPort()); writer.Write(); window.Finalize()
        image = Image.open(path).convert('RGB'); draw = ImageDraw.Draw(image)
        draw.text((24, 24), title, fill=(25, 35, 45), font_size=25)
        images.append(image)
    combined = Image.new('RGB', (2700, 900))
    for i, image in enumerate(images): combined.paste(image, (900*i, 0))
    combined.save(root / 'comparison.png')
