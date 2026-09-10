# SPDX-License-Identifier: MIT OR Apache-2.0
"""Render exported joint motion as MP4/GIF previews using VTK and ffmpeg.

Uses original mesh triangles/material colors and the sidecar's actual joint nodes.
The sweep is an inspection animation, not a simulation of rulebook timing.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_semantics import apply_pose, digest, safe_path
from gltf_scene import accessor, read_glb, scene_nodes
from preview.motion_profiles import demo_coordinate


def vtk_matrix(matrix):
    result = vtk.vtkMatrix4x4()
    for row in range(4):
        for col in range(4):
            result.SetElement(row, col, matrix[row, col])
    return result


def actor_for_primitive(document, binary, primitive):
    if primitive.get('mode', 4) != 4:
        raise ValueError('preview requires triangle primitives')
    points = accessor(document, binary, primitive['attributes']['POSITION'])
    indices = (accessor(document, binary, primitive['indices']) if 'indices' in primitive
               else np.arange(len(points))).reshape(-1, 3)
    used = np.unique(indices)
    points = points[used]
    indices = np.searchsorted(used, indices)
    poly = vtk.vtkPolyData()
    vtkpoints = vtk.vtkPoints()
    vtkpoints.SetData(numpy_to_vtk(np.ascontiguousarray(points), deep=True))
    poly.SetPoints(vtkpoints)
    cells = vtk.vtkCellArray()
    packed = np.column_stack([np.full(len(indices), 3), indices]).astype(np.int64)
    cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(packed.ravel(), deep=True))
    poly.SetPolys(cells)
    if 'NORMAL' in primitive['attributes']:
        normals = accessor(document, binary, primitive['attributes']['NORMAL'])[used]
        poly.GetPointData().SetNormals(numpy_to_vtk(np.ascontiguousarray(normals), deep=True))
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(poly)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    material = document.get('materials', [])[primitive['material']] if 'material' in primitive else {}
    rgba = material.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1])
    rgb = [12.92*c if c <= .0031308 else 1.055*c**(1/2.4)-.055 for c in rgba[:3]]
    prop = actor.GetProperty()
    prop.SetColor(*rgb)
    prop.SetOpacity(rgba[3])
    prop.SetAmbient(.3)
    prop.SetDiffuse(.7)
    prop.SetSpecular(.08)
    prop.SetSpecularPower(20)
    prop.BackfaceCullingOff()
    return actor


def label(renderer, text, x, y, size, color):
    actor = vtk.vtkTextActor()
    actor.SetInput(text)
    actor.SetPosition(x, y)
    prop = actor.GetTextProperty()
    prop.SetFontFamilyToArial()
    prop.SetFontSize(size)
    prop.SetColor(*color)
    renderer.AddViewProp(actor)
    return actor


def sweep_coordinates(joints, phase, time_s=0, active_target_mode=None):
    coordinates = {}
    fraction = .5 - .5 * np.cos(phase)
    for joint in joints:
        if 'demo_motion' in joint:
            value = demo_coordinate(joint, time_s, active_target_mode)
            if value is not None:
                coordinates[joint['id']] = value
            continue
        if joint['type'] == 'continuous':
            value = phase
        else:
            start, end = joint.get('preview_range', joint.get('limits'))
            if joint.get('preview_start') == 'upper':
                start, end = end, start
            value = start + (end - start) * fraction
        coordinates[joint['id']] = value
    return coordinates


def render(package, name, out, fps=20, seconds=6, width=960, height=720, hide_roles=(), hide_layers=(), tech_core_demo=False, presentation=False, core_motion="translation"):
    manifest = json.loads((package / 'manifest.json').read_text())
    record = manifest['articulation']
    path = safe_path(package, record['file'])
    if digest(path) != record['sha256']:
        raise ValueError('sidecar checksum mismatch')
    sidecar = json.loads(path.read_text())
    asset = sidecar['assets'][name]['files']['visual']
    path = safe_path(package, asset['file'])
    if digest(path) != asset['sha256']:
        raise ValueError('GLB checksum mismatch')
    document, binary = read_glb(path)
    joints = asset['joints']
    demo_report, demo_values = None, None
    if tech_core_demo:
        if name != 'tech-core':
            raise ValueError('Technology Core demo requires the tech-core asset')
        from preview.tech_core_demo import prepare_demo, trajectory, complex_trajectory
        document, binary, axes, point, direction, demo_report = prepare_demo(document, binary, asset)
        demo_values, errors = (complex_trajectory if core_motion == "pose-tour" else trajectory)(axes, point, direction, int(round(fps * seconds)))
        demo_report.update(errors)
    if any(j['type'] != 'continuous' and j.get('limits') is None and j.get('preview_range') is None for j in joints):
        raise ValueError('joint preview requires explicit limits or an inspection preview_range')
    renderer = vtk.vtkRenderer()
    renderer.SetBackground(.76, .80, .85)
    renderer.SetBackground2(.95, .96, .98)
    renderer.GradientBackgroundOn()
    if presentation:
        renderer.GradientBackgroundOff()
        renderer.SetBackground(0, 0, 0)
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(width, height)
    window.SetMultiSamples(4)
    window.AddRenderer(renderer)
    actors = {}
    hidden_nodes = []
    bounds = []
    rest_world = {i: world for i, world, _ in scene_nodes(document)}
    for index, world, _ in scene_nodes(document):
        node = document['nodes'][index]
        if 'mesh' not in node:
            continue
        metadata = node.get('extras', {}).get('rm', {})
        if set(hide_roles) & set(metadata.get('roles', [])) or metadata.get('layer') in hide_layers:
            hidden_nodes.append(index)
            continue
        for primitive in document['meshes'][node['mesh']]['primitives']:
            actor = actor_for_primitive(document, binary, primitive)
            actor.SetUserMatrix(vtk_matrix(world))
            renderer.AddActor(actor)
            actors.setdefault(index, []).append(actor)
            bounds.append(actor.GetBounds())
    lo = np.min([[b[0], b[2], b[4]] for b in bounds], axis=0)
    hi = np.max([[b[1], b[3], b[5]] for b in bounds], axis=0)
    center = (lo + hi) / 2
    extent = hi - lo
    # Markers follow each origin frame, including upstream serial joints.
    for joint in ([] if presentation else joints):
        frame = rest_world[joint['origin_node']]
        axis = np.asarray(joint['axis'], dtype=float)
        axis /= np.linalg.norm(axis)
        pivot = np.zeros(3)
        length = max(extent) * (.12 if name == 'tech-core' else .23)
        line = vtk.vtkLineSource()
        line.SetPoint1(*(pivot - axis * length))
        line.SetPoint2(*(pivot + axis * length))
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(line.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(1, .68, .24)
        actor.GetProperty().SetLineWidth(3)
        actor.GetProperty().LightingOff()
        actor.SetUserMatrix(vtk_matrix(frame))
        actors.setdefault(joint['origin_node'], []).append(actor)
        renderer.AddActor(actor)
    camera = renderer.GetActiveCamera()
    z_up = name in {'base', 'dart-station', 'tech-core'}
    direction = np.array([.42, .16, 1.0]) if name == 'rune' else (np.array([-1.6, -1.2, .8]) if z_up else np.array([-1.0, .48, 1.65]))
    camera.SetPosition(*(center + direction * max(extent) * 2.4))
    camera.SetFocalPoint(*center)
    camera.SetViewUp(*( [0, 0, 1] if z_up else [0, 1, 0]))
    camera.ParallelProjectionOn()
    view = direction / np.linalg.norm(direction)
    up = np.array([0., 0., 1.]) if z_up else np.array([0., 1., 0.])
    right = np.cross(up, view); right /= np.linalg.norm(right)
    screen_up = np.cross(view, right)
    corners = np.array([[lo[j] if k & (1 << j) == 0 else hi[j] for j in range(3)] for k in range(8)])
    projected_height = np.ptp(corners @ screen_up)
    projected_width = np.ptp(corners @ right)
    camera.SetParallelScale(max(projected_height * .70, projected_width * .70 * height / width))
    renderer.ResetCameraClippingRange()
    renderer.AutomaticLightCreationOff()
    for direction, intensity in [([2, 3, 4], 1.0), ([-3, 1, -2], .65)]:
        light = vtk.vtkLight()
        light.SetLightTypeToSceneLight()
        light.SetPosition(*(center + np.asarray(direction) * max(extent)))
        light.SetFocalPoint(*center)
        light.SetIntensity(intensity)
        renderer.AddLight(light)
    title = {'outpost': 'OUTPOST  /  rotor joint', 'rune': 'POWER RUNE  /  fixed center, moving arms', 'base': 'BASE  /  protective shield', 'dart-station': 'DART STATION  /  gate travel', 'tech-core': 'TECHNOLOGY CORE  /  joint inspection'}[name]
    if tech_core_demo:
        title = 'TECHNOLOGY CORE / ' + ('pose tour and insertion demo' if core_motion == 'pose-tour' else '100 mm insertion-motion demo')
    label(renderer, title, 28, height-48, 25, (.12, .17, .24))
    frames_only = bool(joints) and all(j.get('geometry_binding') == 'frames_only' for j in joints)
    reconstructed = [i for i, n in enumerate(document['nodes'])
                     if n.get('extras', {}).get('rm', {}).get('geometry_origin') == 'reconstruction']
    if tech_core_demo:
        subtitle = 'CAD links with schematic bearing housings / demo rig'
    elif frames_only:
        subtitle = 'Frames only; CAD geometry is not bound'
    elif hide_roles or hide_layers:
        subtitle = 'Hidden: ' + ', '.join([*hide_roles, *hide_layers])
    elif reconstructed:
        subtitle = 'Source CAD + reconstructed interior / reused armor modules'
    else:
        subtitle = 'Original CAD meshes  |  gold line: joint axis'
    label(renderer, subtitle, 28, height-76, 15, (.32, .39, .48))
    angle_label = label(renderer, '', 28, 48, 23, (.62, .29, .06))
    caption = ('Illustrative opening; inferred interior and armor placement' if reconstructed else
               'Illustrative travel; not calibrated mechanism limits' if name in {'base', 'dart-station', 'tech-core'} else
               '360-degree inspection sweep; not match timing')
    if tech_core_demo:
        caption = 'Rulebook 100 mm translation; direction and timing are illustrative'
    label(renderer, caption, 28, 23, 14, (.32, .39, .48))
    if presentation:
        renderer.RemoveAllViewProps()
        for node_actors in actors.values():
            for actor in node_actors:
                renderer.AddActor(actor)
                actor.GetProperty().SetSpecular(.28)
                actor.GetProperty().SetSpecularPower(35)
        # Fit a sphere around sampled moving geometry, keeping every orbit angle in frame.
        motion_bounds = []
        for sample in range(32):
            phase = 2 * np.pi * sample / 32
            coordinates = (dict(zip([j['id'] for j in joints], demo_values[int(sample * len(demo_values) / 32)]))
                           if tech_core_demo else sweep_coordinates(joints, phase, seconds * sample / 32))
            for index, world, _ in scene_nodes(apply_pose(document, joints, coordinates)):
                for actor in actors.get(index, []):
                    actor.SetUserMatrix(vtk_matrix(world))
                    motion_bounds.append(actor.GetBounds())
        moving_lo = np.min([[b[0], b[2], b[4]] for b in motion_bounds], axis=0)
        moving_hi = np.max([[b[1], b[3], b[5]] for b in motion_bounds], axis=0)
        center = (moving_lo + moving_hi) / 2
        radius = np.linalg.norm(moving_hi - moving_lo) / 2
        camera.ParallelProjectionOff()
        camera.SetViewAngle(32)
        half_angle = min(np.radians(16), np.arctan(np.tan(np.radians(16)) * width / height))
        orbit_distance = radius * 1.12 / np.sin(half_angle)
        orbit_front = view - up * np.dot(view, up)
        orbit_front /= np.linalg.norm(orbit_front)
        orbit_right = np.cross(up, orbit_front)
        renderer.RemoveAllLights()
        # Camera-relative studio lights keep dark CAD surfaces readable throughout the orbit.
        for position, intensity in [((1, 1, 1), 1.0), ((-1, .3, 1), .7), ((0, 1, -1), 1.2)]:
            light = vtk.vtkLight()
            light.SetLightTypeToCameraLight()
            light.SetPosition(*position)
            light.SetFocalPoint(0, 0, 0)
            light.SetIntensity(intensity)
            renderer.AddLight(light)
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(window)
    capture.SetInputBufferTypeToRGB()
    capture.ReadFrontBufferOff()
    out.mkdir(parents=True, exist_ok=True)
    stem = f'{name}-demo' if tech_core_demo else f'{name}-joints'
    if presentation:
        stem += '-orbit'
    mp4 = out / f'{stem}.mp4'
    frames = int(round(fps * seconds))
    command = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', f'{width}x{height}', '-r', str(fps), '-i', '-', '-an', '-c:v', 'libx264',
               '-crf', '19', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(mp4)]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for k in range(frames):
            angle = 2*np.pi*k/frames
            coordinates = (dict(zip([j['id'] for j in joints], demo_values[k])) if tech_core_demo
                           else sweep_coordinates(joints, angle, k/fps))
            posed = apply_pose(document, joints, coordinates)
            for index, world, _ in scene_nodes(posed):
                for actor in actors.get(index, []):
                    actor.SetUserMatrix(vtk_matrix(world))
            value = next(iter(coordinates.values()), 0)
            unit = 'm' if joints and joints[0]['type'] == 'prismatic' else 'deg'
            displayed = value if unit == 'm' else np.degrees(value)
            if tech_core_demo:
                distance_mm = 50 * (1-np.cos(angle))
                angle_label.SetInput(('Pose tour  |  ' + demo_report['stages'][min(int(k / frames * 7), 6)].replace('_', ' ')) if core_motion == 'pose-tour' else f'{distance_mm:05.1f} mm translation  |  6-axis demo rig')
            elif 'base.dart_target.slide' in coordinates:
                angle_label.SetInput(f'Cover {displayed:.3f} m  |  target {coordinates["base.dart_target.slide"]:+.3f} m  |  demo')
            else:
                angle_label.SetInput(f'{displayed:06.3f} {unit}   |   {len(joints)} exported joint(s)')
            if presentation:
                orbit_direction = (np.cos(angle) * orbit_front + np.sin(angle) * orbit_right) * np.cos(np.radians(18)) + up * np.sin(np.radians(18))
                camera.SetPosition(*(center + orbit_direction * orbit_distance))
                camera.SetFocalPoint(*center)
                camera.SetViewUp(*up)
                renderer.ResetCameraClippingRange()
            window.Render()
            capture.Modified()
            capture.Update()
            data = capture.GetOutput()
            pixels = vtk_to_numpy(data.GetPointData().GetScalars()).reshape(height, width, 3)[::-1].copy()
            encoder.stdin.write(pixels.tobytes())
            if k in {0, frames//8, frames//4, frames//2, 3*frames//4}:
                from PIL import Image
                Image.fromarray(pixels).save(out / f'{stem}-{k:03}.png')
            if k % fps == 0:
                print(f'{name}: frame {k}/{frames}', flush=True)
    finally:
        encoder.stdin.close()
        result = encoder.wait()
        window.Finalize()
    if result:
        raise RuntimeError('ffmpeg video encoding failed')
    gif = out / f'{stem}.gif'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(mp4), '-filter_complex',
                    'fps=15,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a',
                    '-loop', '0', str(gif)], check=True)
    report = {'asset': name, 'input_visual_sha256': asset['sha256'],
              'articulation_sha256': record['sha256'], 'joints': [j['id'] for j in joints],
              'hidden_roles': list(hide_roles), 'hidden_layers': list(hide_layers), 'hidden_nodes': hidden_nodes,
              'reconstructed_nodes': reconstructed,
              'presentation': {'background': 'black' if presentation else 'gradient',
                               'overlays': not presentation, 'camera': '360-degree perspective orbit' if presentation else 'fixed orthographic'},
              'fps': fps, 'seconds': seconds, 'frames': frames, 'size': [width, height],
              'motion': (('IK pose tour with a fixed-orientation 100 mm insertion segment' if core_motion == 'pose-tour' else 'IK-driven 100 mm tool translation with fixed orientation') if tech_core_demo else
                         'demo_motion profiles where present; otherwise continuous 2*pi or bounded cosine inspection sweeps'),
              'geometry_binding': 'preview_only_rig' if tech_core_demo else 'frames_only' if frames_only else 'mesh_nodes',
              'technology_core_demo': demo_report,
              'demo_motion': {j['id']: j['demo_motion'] for j in joints if 'demo_motion' in j},
              'timing': 'inspection sweep, not rulebook timing',
              'files': {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in [mp4, gif]}}
    (out / f'{stem}.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--asset', choices=['outpost', 'rune', 'base', 'dart-station', 'tech-core'], required=True)
    parser.add_argument('--out', type=Path, default=Path('out/joint-previews'))
    parser.add_argument('--core-motion', choices=['translation', 'pose-tour'], default='translation', help='Technology Core demo trajectory')
    parser.add_argument('--presentation', action='store_true', help='Black background, no overlays or joint markers, perspective camera orbit; source artwork remains')
    parser.add_argument('--tech-core-demo', action='store_true', help='Preview CAD links with schematic bearings performing a 100 mm translation; does not edit the reference rig')
    parser.add_argument('--hide-layer', action='append', default=[], help='Hide directly tagged mesh nodes on a semantic layer for inspection')
    parser.add_argument('--hide-role', action='append', default=[], help='Hide directly tagged mesh nodes for inspection; does not edit the GLB or collision.')
    parser.add_argument('--seconds', type=float, default=6)
    parser.add_argument('--fps', type=int, default=20)
    args = parser.parse_args()
    if args.seconds <= 0 or args.fps <= 0 or args.seconds * args.fps < 4:
        parser.error('positive duration/fps with at least four frames required')
    render(args.package, args.asset, args.out, args.fps, args.seconds, hide_roles=args.hide_role, hide_layers=args.hide_layer, tech_core_demo=args.tech_core_demo, presentation=args.presentation, core_motion=args.core_motion)


if __name__ == '__main__':
    main()
