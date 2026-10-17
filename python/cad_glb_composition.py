# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Rigid GLB definition composition with byte-preserved buffers and real mesh reuse.

The supported contract is embedded, non-sparse rigid triangle meshes, ordinary
PBR materials/textures and optional KHR_materials_unlit. Unsupported references
are rejected rather than silently lost. Source node extras and transforms stay.
"""
import copy
import numpy as np
from gltf_scene import accessor, scene_nodes


class RigidComposer:
    """Append each definition once; instantiate node trees with shared mesh handles."""
    def __init__(self):
        self.document = {'asset': {'version': '2.0', 'generator': 'cad_glb_composition.py',
                                  'copyright': 'DJI / RoboMaster source geometry and appearance'},
                         'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [],
                         'accessors': [], 'bufferViews': [], 'buffers': [{'byteLength': 0}],
                         'materials': [], 'images': [], 'textures': [], 'samplers': []}
        self.binary = bytearray(); self.definitions = {}

    def append_definition(self, name, document, binary):
        """Import one supported GLB and independently verify copied attribute/image bytes."""
        if name in self.definitions: raise ValueError('duplicate composition definition')
        source = copy.deepcopy(document); d = self.document
        if source.get('animations') or source.get('skins') or source.get('extensions') or set(source.get('extensionsUsed', [])) - {'KHR_materials_unlit'} or set(source.get('extensionsRequired', [])) - {'KHR_materials_unlit'}:
            raise ValueError('unsupported animated/extended definition')
        if len(source.get('buffers', [])) != 1 or 'uri' in source['buffers'][0]: raise ValueError('expected one embedded buffer')
        list(scene_nodes(source))  # Reject cycles and invalid scene ownership before copying.
        for node in source['nodes']:
            if any(k in node for k in ['skin', 'weights', 'camera', 'extensions']): raise ValueError('unsupported node references')
        for mesh in source['meshes']:
            if mesh.get('weights') or mesh.get('extensions'): raise ValueError('unsupported mesh references')
            for p in mesh['primitives']:
                if p.get('mode', 4) != 4 or 'targets' in p or p.get('extensions'): raise ValueError('unsupported primitive')
        offsets = {k: len(d[k]) for k in ['accessors', 'bufferViews', 'materials', 'images', 'textures', 'samplers', 'meshes']}
        self.binary.extend(b'\0' * (-len(self.binary) % 4)); byte_offset = len(self.binary); self.binary.extend(binary)
        for view in source.get('bufferViews', []):
            if view.get('buffer', 0) != 0 or view.get('extensions'): raise ValueError('unsupported buffer view')
            v = copy.deepcopy(view); v['buffer'] = 0; v['byteOffset'] = v.get('byteOffset', 0) + byte_offset; d['bufferViews'].append(v)
        for old_index, value in enumerate(source.get('accessors', [])):
            if 'sparse' in value or 'bufferView' not in value or value.get('extensions'): raise ValueError('unsupported accessor')
            v = copy.deepcopy(value); v['bufferView'] += offsets['bufferViews']; d['accessors'].append(v)
            if not np.array_equal(accessor(source, binary, old_index), accessor(d, self.binary, old_index + offsets['accessors'])):
                raise ValueError('copied accessor differs')
        for image in source.get('images', []):
            if 'uri' in image or 'bufferView' not in image or image.get('extensions'): raise ValueError('unsupported image')
            v = copy.deepcopy(image); v['bufferView'] += offsets['bufferViews']; d['images'].append(v)
            old = source['bufferViews'][image['bufferView']]; new = d['bufferViews'][v['bufferView']]
            if binary[old.get('byteOffset', 0):old.get('byteOffset', 0) + old['byteLength']] != self.binary[new['byteOffset']:new['byteOffset'] + new['byteLength']]: raise ValueError('copied image differs')
        d['samplers'].extend(copy.deepcopy(source.get('samplers', [])))
        for texture in source.get('textures', []):
            if texture.get('extensions'): raise ValueError('unsupported texture')
            v = copy.deepcopy(texture); v['source'] += offsets['images']
            if 'sampler' in v: v['sampler'] += offsets['samplers']
            d['textures'].append(v)
        for material in source.get('materials', []):
            if set(material.get('extensions', {})) - {'KHR_materials_unlit'}: raise ValueError('unsupported material extension')
            v = copy.deepcopy(material)
            slots = [v.get('pbrMetallicRoughness', {})]
            for container, keys in [(slots[0], ['baseColorTexture', 'metallicRoughnessTexture']), (v, ['normalTexture', 'occlusionTexture', 'emissiveTexture'])]:
                for key in keys:
                    if key in container:
                        if container[key].get('extensions'): raise ValueError('unsupported texture-info extension')
                        container[key]['index'] += offsets['textures']
            d['materials'].append(v)
        for mesh in source.get('meshes', []):
            v = copy.deepcopy(mesh)
            for primitive in v['primitives']:
                primitive['attributes'] = {k: index + offsets['accessors'] for k, index in primitive['attributes'].items()}
                if 'indices' in primitive: primitive['indices'] += offsets['accessors']
                if 'material' in primitive: primitive['material'] += offsets['materials']
            d['meshes'].append(v)
        for key in ['extensionsUsed', 'extensionsRequired']:
            for value in source.get(key, []):
                if value not in d.setdefault(key, []): d[key].append(value)
        # Template node references are kept definition-local; instances remap children only.
        template = copy.deepcopy(source['nodes'])
        for node in template:
            if 'mesh' in node: node['mesh'] += offsets['meshes']
        roots = source['scenes'][source.get('scene', 0)]['nodes']
        self.definitions[name] = (template, roots)
        d['buffers'][0]['byteLength'] = len(self.binary)
        return {'accessors_verified': len(source.get('accessors', [])),
                'images_verified': len(source.get('images', [])), 'mesh_definitions': len(source['meshes'])}

    def instantiate(self, name, parent, *, extras=None):
        """Clone source node metadata/transforms, sharing every imported mesh/buffer."""
        template, roots = self.definitions[name]; d = self.document; offset = len(d['nodes'])
        for value in template:
            node = copy.deepcopy(value)
            if 'children' in node: node['children'] = [offset + child for child in node['children']]
            if extras: node.setdefault('extras', {}).update(extras)
            d['nodes'].append(node)
        d['nodes'][parent].setdefault('children', []).extend(offset + root for root in roots)
        return [offset + root for root in roots]
