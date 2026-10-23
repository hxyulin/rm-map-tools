# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Repackage reviewed source parts as a named, instanced STEP assembly.

Geometry/topology records retain their original IDs and bytes. Each work part
gets a private product, representation, style and metadata namespace, including
its narrowed surface-model wrappers. This prevents shared wrapper IDs from
merging disjoint shell selections when they enter one STEP file.
"""
import argparse
from collections import defaultdict, Counter
import gc
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

import numpy as np
from cad_components import build_catalog
from cad_composition import compile_compositions, product_occurrences
from cad_document import CadDocument
from cad_partition import compile_partition
from export_step_elements import Assembly, p21_string, real
from p21index import Index, TOK
from p21model import STR_RE
from p21split import Splitter, forward_closure
import provenance


def remap_record(text, mapping):
    """Remap entity IDs/references without touching quoted strings or comments."""
    return TOK.sub(lambda match: b'#'+str(mapping.get(int(match.group(1)),int(match.group(1)))).encode()
                   if match.group(1) is not None else match.group(0), text)


def verify_assembly_graph(index, assemblies):
    """Compare every encoded STEP assembly edge/pose to the intended hierarchy."""
    from mesh_parts import nauo_transforms
    products = {int(index.ids[r]) for r in index.rows_of('PRODUCT')}
    formation = {int(index.ids[r]):next(int(i) for i in index.refs_of(r) if int(i) in products)
                 for r in index.rows_of('PRODUCT_DEFINITION_FORMATION','PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE')}
    definitions = {int(index.ids[r]):next(formation[int(i)] for i in index.refs_of(r) if int(i) in formation)
                   for r in index.rows_of('PRODUCT_DEFINITION','PRODUCT_DEFINITION_WITH_ASSOCIATED_DOCUMENTS')}
    edges = {int(r):(definitions[int(index.refs_of(r)[0])],definitions[int(index.refs_of(r)[1])])
             for r in index.rows_of('NEXT_ASSEMBLY_USAGE_OCCURRENCE')}
    transforms = nauo_transforms(index,SimpleNamespace(nauo=edges))
    expected_count = sum(len(a['children']) for a in assemblies)
    if len(edges)!=expected_count or len(transforms)!=expected_count:
        raise ValueError('encoded assembly edge coverage changed')
    for assembly in assemblies:
        actual = [(child,transforms[row]) for row,(parent,child) in edges.items() if parent==assembly['product_id']]
        if len(actual)!=len(assembly['children']): raise ValueError('assembly child count changed')
        for (child,matrix),expected in zip(actual,assembly['children']):
            if child!=expected['product_id'] or not np.allclose(matrix,expected['matrix_mm'],rtol=0,atol=1e-7):
                raise ValueError('encoded assembly child or pose changed')
    return expected_count


def verify_source_placements(assemblies, root_product_id, product_definitions, source_occurrences):
    """Require every source whole-product world pose exactly once, in source mm."""
    by_id = {a['product_id']:a for a in assemblies}
    source_of = {export_id:int(source_id) for source_id,export_id in product_definitions.items()}
    actual = defaultdict(list)
    def walk(product,matrix,path):
        if product in path: raise ValueError('cycle in hierarchical assembly')
        if product in source_of:
            actual[source_of[product]].append(matrix)
            return
        for child in by_id[product]['children']:
            walk(child['product_id'],matrix@np.array(child['matrix_mm']),path|{product})
    walk(root_product_id,np.eye(4),set())
    for occurrence in source_occurrences:
        matrices = actual[occurrence['product_id']]
        match = next((i for i,m in enumerate(matrices) if np.allclose(m,occurrence['source_world_matrix'],rtol=0,atol=1e-7)),None)
        if match is None: raise ValueError('source world placement changed or disappeared')
        matrices.pop(match)
    if any(actual.values()): raise ValueError('extra source product placement')


class StepTree:
    """Append named synthetic assembly products using rigid AP214 placements."""
    def __init__(self, stream, first_id, contexts):
        self.stream, self.next_id, self.contexts = stream, first_id, contexts
        self.assemblies = []

    def reserve(self, count):
        first = self.next_id; self.next_id += count
        return first

    def add(self, text):
        entity = self.reserve(1)
        self.stream.write(f'#{entity}={text};\n'.encode())
        return entity

    def axis(self, matrix):
        matrix = np.array(matrix, float)
        if (matrix.shape != (4,4) or not np.isfinite(matrix).all()
                or not np.allclose(matrix[3], [0,0,0,1], atol=1e-10)
                or not np.allclose(matrix[:3,:3].T@matrix[:3,:3], np.eye(3), atol=1e-8)
                or not np.isclose(np.linalg.det(matrix[:3,:3]),1,atol=1e-8)):
            raise ValueError('STEP hierarchy placement must be a finite rigid proper transform')
        def vector(kind, values):
            return self.add(f"{kind}('',({','.join(real(v) for v in values)}))")
        point = vector('CARTESIAN_POINT',matrix[:3,3])
        z = vector('DIRECTION',matrix[:3,2]); x = vector('DIRECTION',matrix[:3,0])
        return self.add(f"AXIS2_PLACEMENT_3D('',#{point},#{z},#{x})")

    def assembly(self, name, children):
        """children contains (part handle, child-to-parent matrix in source mm)."""
        if not children: raise ValueError('empty synthetic assembly')
        root_axis = self.axis(np.eye(4))
        axes = [self.axis(np.array(matrix)@child['axis_matrix']) for child,matrix in children]
        sr = self.add(f"SHAPE_REPRESENTATION('',({','.join('#'+str(i) for i in [root_axis,*axes])}),#{self.contexts['representation']})")
        product = self.add(f"PRODUCT({p21_string(name)},{p21_string(name)},'',(#{self.contexts['product']}))")
        pdf = self.add(f"PRODUCT_DEFINITION_FORMATION('','',#{product})")
        pd = self.add(f"PRODUCT_DEFINITION('','',#{pdf},#{self.contexts['definition']})")
        pds = self.add(f"PRODUCT_DEFINITION_SHAPE('','',#{pd})")
        self.add(f'SHAPE_DEFINITION_REPRESENTATION(#{pds},#{sr})')
        self.add(f"PRODUCT_RELATED_PRODUCT_CATEGORY('assembly','',(#{product}))")
        for i, ((child,matrix),axis) in enumerate(zip(children,axes)):
            label = p21_string(f'{name}/{child["name"]}:{i}')
            occurrence = self.add(f'NEXT_ASSEMBLY_USAGE_OCCURRENCE({label},{label},\'\',#{pd},#{child["pd"]},$)')
            shape = self.add(f"PRODUCT_DEFINITION_SHAPE('','',#{occurrence})")
            transform = self.add(f"ITEM_DEFINED_TRANSFORMATION('','',#{child['axis']},#{axis})")
            relation = self.add(f"(REPRESENTATION_RELATIONSHIP('','',#{child['sr']},#{sr})REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(#{transform})SHAPE_REPRESENTATION_RELATIONSHIP())")
            self.add(f'CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(#{relation},#{shape})')
        handle = {'name':name,'product':product,'pd':pd,'sr':sr,'axis':root_axis,'axis_matrix':np.eye(4)}
        self.assemblies.append({'name':name,'product_id':product,'children':[{'product_id':c['product'],'matrix_mm':np.array(m).tolist()} for c,m in children]})
        return handle


def _group_tree(writer, name, leaves):
    """Preserve slash-separated work paths as actual intermediate assemblies."""
    direct, branches = [], {}
    for path,handle in leaves:
        head,*tail = path
        if tail: branches.setdefault(head,[]).append((tail,handle))
        else: direct.append((handle,np.eye(4)))
    if {handle['name'] for handle,_ in direct} & set(branches):
        raise ValueError('work part path overlaps an intermediate assembly')
    for key,items in sorted(branches.items()):
        direct.append((_group_tree(writer,key,items),np.eye(4)))
    return writer.assembly(name,direct)


def write_hierarchy(document, catalog, partitions, compositions, hierarchy_policy, out):
    """Write the full field once, keeping original analytic geometry and styles.

    Whole solids and surface shells remain intact unless reviewed motion ownership
    separates complete original faces into disjoint open surface patches.
    This builds an organizational hierarchy, not mechanical joints or motion.
    Returns a source-identity report after text-level preservation validation.
    """
    out = Path(out); out.mkdir(parents=True,exist_ok=False)
    ix, model = document.index, document.model
    products = [p for partition in partitions for p in partition['products']]
    owned = {c['product_id'] for c in catalog['components']}
    if (catalog['source_sha256'] != document.source_sha256
            or any(p['source_sha256'] != document.source_sha256 for p in partitions)
            or {p['product_id'] for p in products} != owned
            or len(products) != len(owned)):
        raise ValueError('hierarchy must cover every source product exactly once')
    all_faces = {int(ix.ids[f]) for f in ix.rows_of('ADVANCED_FACE')}
    face_counts=Counter(f for p in products for g in p['groups'] for f in g['face_ids'])
    if set(face_counts) != all_faces or any(n!=1 for n in face_counts.values()):
        raise ValueError('hierarchy partitions do not cover every source face')
    splitter = Splitter(ix,model)
    helper = Assembly(ix,model,ix.max_id+1)
    geometry = forward_closure(ix,[b for b,_ in model.bodies],np.zeros(ix.n,bool))
    # Surface wrappers are private to each shell subset. Their descendants are
    # immutable original geometry and can retain globally shared source IDs.
    geometry[ix.rows_of('SHELL_BASED_SURFACE_MODEL')] = False
    patch_bodies={int(b) for p in products for g in p['groups'] for b in g.get('face_ids_by_body',{})}
    private_patch_wrappers=set()
    for body in patch_bodies:
        private_patch_wrappers.add(ix.r(body))
        private_patch_wrappers.update(shell for _,shell in model.body_faces_shells(ix.r(body)))
        private_patch_wrappers.update(ix.r(int(ref)) for ref in ix.refs_of(ix.r(body))
                                      if ix.tname(ix.r(int(ref)))=='ORIENTED_CLOSED_SHELL')
    for row in private_patch_wrappers:geometry[row]=False
    rows = np.flatnonzero(geometry)
    for row in rows:
        if any(not geometry[ix.r(int(ref))] for ref in ix.refs_of(int(row))):
            raise ValueError(f'shared geometry #{int(ix.ids[row])} {ix.tname(row)} depends on private wrapper {[int(ref) for ref in ix.refs_of(int(row)) if not geometry[ix.r(int(ref))]]}')
    source_digest = hashlib.sha256()
    product_handles, component_records = {}, []
    path = out/'field.step'
    with path.open('wb') as stream:
        stream.write(provenance.step_header(ix.header,path.name,'cad_hierarchy.py',document.source_path,
                                           document.source_sha256,'Reviewed source-owned field hierarchy; no geometry approximation')+b'\n')
        for row in rows:
            raw = ix.text(int(row)); stream.write(raw+b'\n'); source_digest.update(raw+b'\n')
        writer = StepTree(stream,ix.max_id+1,{})
        for product in products:
            pid = product['product_id']; source_row = ix.r(pid)
            pd_row, sr_row = helper.pd_of[source_row], helper.sr_of[source_row]
            axis_id, axis_matrix = helper.child_axis(sr_row)
            leaves = []
            for group in product['groups']:
                bodies = set(group['solid_body_ids']) | {int(b) for b in group['shell_ids_by_body']} | {int(b) for b in group.get('face_ids_by_body',{})}
                shells = {int(b):ids for b,ids in group['shell_ids_by_body'].items()}
                mask, rewritten = splitter.closure_products([source_row],body_ids=bodies,shell_ids_by_body=shells,face_ids_by_body={int(b):ids for b,ids in group.get('face_ids_by_body',{}).items()})
                private_rows = np.flatnonzero(mask & ~geometry)
                first = writer.reserve(len(private_rows))
                mapping = {int(ix.ids[row]):first+i for i,row in enumerate(private_rows)}
                export_id = lambda row: mapping.get(int(ix.ids[row]),int(ix.ids[row]))
                # Context references of synthetic parents must resolve to this
                # part's copied contexts rather than the discarded source PDM.
                if not writer.contexts:
                    writer.contexts = {key:mapping.get(helper.last_ref(row),helper.last_ref(row))
                                       for key,row in [('product',source_row),('definition',pd_row),('representation',sr_row)]}
                name = group['id'].split('/')[-1]
                for row in private_rows:
                    raw = rewritten.get(int(row),ix.text(int(row)))
                    if int(row)==source_row:
                        literal = p21_string(name).encode()
                        raw = STR_RE.sub(lambda _:literal,raw,count=2)
                    stream.write(remap_record(raw,mapping)+b'\n')
                axis = mapping.get(axis_id,axis_id) if axis_id is not None else writer.axis(np.eye(4))
                handle = {'name':name,'product':export_id(source_row),'pd':export_id(pd_row),
                          'sr':export_id(sr_row),'axis':axis,'axis_matrix':axis_matrix}
                parts = group['id'].split('/')
                if parts[0] != product['name']: raise ValueError('group path outside its product')
                leaves.append((parts[1:],handle))
                component_records.append({**group,'source_product_id':pid,'export_product_id':handle['product'],
                    'first_private_entity_id':first,'private_source_entity_ids':[int(ix.ids[r]) for r in private_rows],
                    'export_body_ids':{str(b):mapping.get(b,b) for b in sorted(bodies)}})
            product_handles[pid] = _group_tree(writer,product['name'],leaves)
            print('hierarchy product',product['name'],len(leaves),'work parts',flush=True)
        occurrences = product_occurrences(catalog)
        identity = lambda o:(o['root_product_id'],tuple(o['occurrence_path']),o['product_id'])
        consumed, equipment = set(), []
        bounds = {}
        for component in catalog['components']:
            low,high,_ = model.body_bbox(ix.r(component['body_id']))
            if low is None: raise ValueError('source body has no finite placement bounds')
            bounds.setdefault(component['product_id'],[]).extend(np.array([x,y,z]) for x in [low[0],high[0]] for y in [low[1],high[1]] for z in [low[2],high[2]])
        for recipe in compositions:
            selected = recipe['occurrences']
            for occurrence in selected:
                key=identity(occurrence)
                if key in consumed: raise ValueError('compositions overlap source occurrences')
                consumed.add(key)
            placed = [np.array(bounds[o['product_id']])@np.array(o['source_world_matrix'])[:3,:3].T+np.array(o['source_world_matrix'])[:3,3] for o in selected]
            low=np.min([p.min(0) for p in placed],axis=0); high=np.max([p.max(0) for p in placed],axis=0)
            anchor=np.eye(4); anchor[:3,3]=(low+high)/2; anchor[2,3]=low[2]
            items=[(product_handles[o['product_id']],np.linalg.inv(anchor)@np.array(o['source_world_matrix'])) for o in selected]
            equipment.append((writer.assembly(recipe['name'],items),anchor))
        categories={'equipment':equipment,'terrain':[],'fixtures':[]}
        for occurrence in occurrences:
            if identity(occurrence) in consumed: continue
            consumed.add(identity(occurrence)); pid=occurrence['product_id']
            category = 'fixtures' if pid in hierarchy_policy['secondary_product_ids'] else 'equipment' if pid in hierarchy_policy['equipment_product_ids'] else 'terrain'
            categories[category].append((product_handles[pid],np.array(occurrence['source_world_matrix'])))
        if len(consumed)!=len(occurrences): raise ValueError('source occurrence coverage changed')
        root=writer.assembly(hierarchy_policy['name'],[(writer.assembly(name,children),np.eye(4)) for name,children in categories.items() if children])
        stream.write(b'ENDSEC;\nEND-ISO-10303-21;\n')
    # Reparse independently. Original geometry has original IDs/bytes; private
    # records must be the exact filtered source text under a reference remap.
    with Index.from_step(path,workers=1) as check:
        if np.any(check.row[check.refs]<0): raise ValueError('hierarchical STEP has dangling references')
        if {int(check.ids[f]) for f in check.rows_of('ADVANCED_FACE')} != all_faces:
            raise ValueError('hierarchical STEP source face identities changed')
        actual_digest=hashlib.sha256()
        for row in rows:
            source_id=int(ix.ids[row]); actual_digest.update(check.text(check.r(source_id))+b'\n')
        if actual_digest.digest()!=source_digest.digest(): raise ValueError('source geometry bytes changed')
        for component in component_records:
            source_row=ix.r(component['source_product_id']); bodies=set(component['export_body_ids'])
            mask,rewritten=splitter.closure_products([source_row],body_ids=set(map(int,bodies)),
                shell_ids_by_body={int(b):ids for b,ids in component['shell_ids_by_body'].items()},
                face_ids_by_body={int(b):ids for b,ids in component.get('face_ids_by_body',{}).items()})
            mapping={source_id:component['first_private_entity_id']+i for i,source_id in enumerate(component['private_source_entity_ids'])}
            for source_id,export_id in mapping.items():
                raw=rewritten.get(ix.r(source_id),ix.text(ix.r(source_id)))
                if source_id==component['source_product_id']:
                    literal=p21_string(component['id'].split('/')[-1]).encode(); raw=STR_RE.sub(lambda _:literal,raw,count=2)
                if check.text(check.r(export_id))!=remap_record(raw,mapping): raise ValueError('private style/metadata record changed unexpectedly')
        verify_assembly_graph(check,writer.assemblies)
    verify_source_placements(writer.assemblies,root['product'],
                             {pid:handle['product'] for pid,handle in product_handles.items()},occurrences)
    document.verify_source()
    by_product={c['id']:c for c in catalog['components']}
    placed_faces=sum(by_product[o['component_id']]['source_faces'] for o in catalog['occurrences'])
    report={'schema_version':1,'source_sha256':document.source_sha256,'source_geometry_preserved':True,
            'assembly_graph_verified':True,'source_world_placements_verified':True,
            'geometry_record_sha256':source_digest.hexdigest(),'original_geometry_records':len(rows),
            'source_face_definitions':len(all_faces),'expected_placed_faces':placed_faces,
            'source_body_definitions':len(catalog['components']),'source_placed_bodies':len(catalog['occurrences']),
            'source_product_occurrences':len(occurrences),'work_part_definitions':len(component_records),
            'source_occurrences':occurrences,
            'source_product_definitions':{str(pid):handle['product'] for pid,handle in product_handles.items()},
            'coordinate_contract':'Original source assembly frame, millimetres, Z up; no geometric re-encoding or tessellation.',
            'source_motion':hierarchy_policy.get('prepared_motion'),
            'face_patch_body_ids':sorted(patch_bodies),
            'private_patch_wrapper_ids':sorted(int(ix.ids[r]) for r in private_patch_wrappers),
            'root_product_id':root['product'],'components':component_records,'assemblies':writer.assemblies,
            'limitations':['Rest-pose source motion groups/metadata only; no controllers, animated poses, scoring or runtime collision bindings.',
                           'Whole solids stay whole except listed face_patch_body_ids, represented by disjoint original open face patches; no caps or new faces.',
                           'Leaf definitions retain original product coordinates. Equipment compositions get translated local origins.']}
    shutil.copyfile(Path(__file__).resolve().parents[1]/'NOTICE.md',out/'NOTICE.md')
    report['files_sha256']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['field.step','NOTICE.md']}
    (out/'hierarchy.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def native_validate(out):
    """Read native geometry/names and check placed face coverage.

    Full appearance records are checked by the text preservation proof and the
    colored nested-instance regression. Expanding per-face presentation labels
    in the entire field is unnecessary for this geometry/assembly coverage check.
    """
    from export_step_elements import shape_counts
    from cad_composition import native_bounds_m
    from validate_parts import (TDF_LabelSequence,XCAFDoc_DocumentTool,TDocStd_Document,
                                TCollection_ExtendedString,STEPCAFControl_Reader,IFSelect_RetDone)
    out=Path(out); report=json.loads((out/'hierarchy.json').read_text())
    native=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    reader=STEPCAFControl_Reader()
    for mode in ('Color','Layer','Props','Mat','GDT','SHUO','View','Meta','ProductMeta'):
        setter=getattr(reader,'Set'+mode+'Mode',None)
        if setter is not None: setter(False)
    reader.SetNameMode(True)
    if reader.ReadFile(str(out/'field.step'))!=IFSelect_RetDone or not reader.Transfer(native):
        raise ValueError('native geometry/assembly transfer failed')
    roots=TDF_LabelSequence(); tool=XCAFDoc_DocumentTool.ShapeTool_s(native.Main());tool.GetFreeShapes(roots)
    counts=shape_counts(native)
    if roots.Length()!=1 or not tool.IsAssembly_s(roots.Value(1)) or counts[1]!=report['expected_placed_faces']:
        raise ValueError(f'native hierarchy coverage changed: roots={roots.Length()}, counts={counts}')
    result={'single_root_assembly':True,'native_solids':counts[0],'native_faces':counts[1],
            'transfer_scope':'geometry and assembly names; presentation checked separately',
            'bounds_m':native_bounds_m(native).tolist()}
    (out/'native-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--validate-native',action='store_true',help='also read the entire STEP assembly through XCAF')
    args=parser.parse_args()
    policy=json.loads(args.policy.read_text()); base=args.policy.parent
    if policy.get('schema_version')!=1: raise ValueError('unsupported hierarchy policy')
    if args.out.exists(): raise ValueError('output exists')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    inputs={name:json.loads((base/policy[name]).read_text()) for name in ['components','motion_profile','regions','compositions']}
    partition_policies=[json.loads((base/name).read_text()) for name in policy['partitions']]
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        stage=Path(tmp)/'hierarchy'
        loader=CadDocument.from_index if args.source.suffix=='.npz' else CadDocument.from_step
        with loader(args.source,expected_sha256=policy['source_sha256']) as document:
            prepared_motion=None
            if policy.get('source_motion'):
                from cad_motion import compile_source_motion
                prepared_motion=compile_source_motion(document,json.loads((base/policy['source_motion']).read_text()))
            catalog=build_catalog(document,inputs['components'],inputs['motion_profile'],inputs['regions'])
            partitions=[compile_partition(document,catalog,p,source_motion=prepared_motion) for p in partition_policies]
            covered={p['product_id'] for part in partitions for p in part['products']}
            missing={c['product_id'] for c in catalog['components']}-covered
            if missing!=set(policy['whole_product_fallbacks']): raise ValueError('unexpected unpartitioned products')
            if missing:
                specs=[]
                for pid in sorted(missing):
                    name=inputs['components']['product_names'][str(pid)]
                    groups={c['group']:name+'/source-model' for c in catalog['components'] if c['product_id']==pid}
                    specs.append({'name':name,'product_id':pid,'fallback_group':name+'/source-model','body_group_overrides':groups})
                partitions.append(compile_partition(document,catalog,{'schema_version':1,'source_sha256':document.source_sha256,'length_unit':'millimetre','products':specs},source_motion=prepared_motion))
            if prepared_motion:
                prepared_motion={k:v for k,v in prepared_motion.items() if k!='face_owners'}
            recipes=compile_compositions(catalog,inputs['compositions'])
            report=write_hierarchy(document,catalog,partitions,recipes,{**policy,'prepared_motion':prepared_motion,'secondary_product_ids':inputs['compositions']['secondary_product_ids']},stage)
        del document,catalog,partitions;gc.collect()
        print('source preservation and assembly placement checks passed',flush=True)
        if args.validate_native:
            print('reading complete hierarchy through native XCAF',flush=True)
            print('native validation',native_validate(stage),flush=True)
        stage.rename(args.out)
    print('wrote',args.out/'field.step',report['work_part_definitions'],'work definitions',flush=True)


if __name__=='__main__':main()
