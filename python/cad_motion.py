# SPDX-License-Identifier: MIT OR Apache-2.0
"""Prepare reviewed source motion ownership before hierarchy grouping.

Select original body/shell/face IDs only. No native import, fitting, tessellation,
geometry modification or simulation controller is performed here.
"""
import re


def compile_source_motion(document, policy):
    if policy.get('schema_version') != 1 or policy.get('source_sha256') != document.source_sha256:
        raise ValueError('source motion policy schema/source SHA-256 mismatch')
    ix, model = document.index, document.model
    bodies = {}
    for body, rep in model.bodies:
        product = model.rep_product.get(rep)
        if product is not None:
            bodies[int(ix.ids[body])] = int(ix.ids[product])
    for pid,group in policy.get('product_defaults',{}).items():
        if int(pid) not in set(bodies.values()) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)+',group):
            raise ValueError('invalid source motion product default')
    owners, records, seen = {}, [], set()
    joints = {j['id']:j for j in policy.get('joints', [])}
    if len(joints) != len(policy.get('joints', [])):
        raise ValueError('duplicate source motion joint')
    import math
    for joint in joints.values():
        axis=joint.get('axis_product_local')
        if axis is not None and (len(axis)!=3 or any(not math.isfinite(x) for x in axis)
                                 or abs(sum(x*x for x in axis)-1)>1e-8):
            raise ValueError('motion joint axis must be finite and normalized')
    for selection in policy['selections']:
        pid, group = selection['product_id'], selection['group']
        if (not re.fullmatch(r'[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)+',group)
                or not selection.get('evidence') or group in seen):
            raise ValueError('motion selection needs unique safe group and evidence')
        seen.add(group)
        owner = selection.get('motion_owner')
        if owner is not None and (owner not in joints or joints[owner]['source_product_id'] != pid):
            raise ValueError('unknown or wrong-product motion owner')
        faces = set()
        for unit in selection['units']:
            body = unit['body_id']
            if bodies.get(body) != pid:
                raise ValueError('motion unit is outside its product')
            all_faces = {int(ix.ids[f]) for f in model.body_faces(ix.r(body))}
            kinds = set(unit)-{'body_id'}
            if kinds == {'shell_id'}:
                shell=unit['shell_id']
                if (ix.tname(ix.r(body)) != 'SHELL_BASED_SURFACE_MODEL'
                        or shell not in set(map(int,ix.refs_of(ix.r(body))))):
                    raise ValueError('motion shell is outside its body')
                selected={int(ix.ids[f]) for f in model.body_faces(ix.r(shell))}
            elif kinds == {'face_ids'}:
                selected=set(unit['face_ids'])
                if len(selected)!=len(unit['face_ids']):raise ValueError('duplicate motion face')
            elif not kinds:
                selected=all_faces
            else:
                raise ValueError('motion unit requires one body, shell or face selector')
            if not selected or not selected <= all_faces or faces & selected:
                raise ValueError('empty, foreign or overlapping motion faces')
            faces |= selected
        for face in faces:
            if face in owners:raise ValueError('source face assigned to multiple motion groups')
            owners[face]={'group':group,'motion_owner':owner,'product_id':pid}
        records.append({**selection,'source_face_ids':sorted(faces),'source_face_count':len(faces)})
    document.verify_source()
    return {'schema_version':1,'source_sha256':document.source_sha256,
            'geometry_modified':False,'selections':records,'joints':list(joints.values()),
            'face_owners':owners,'product_defaults':policy.get('product_defaults',{}),
            'coordinates':'original product-local millimetres; source occurrence transforms remain authoritative'}


def main():
    import argparse
    import json
    from pathlib import Path
    from cad_document import CadDocument
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise ValueError('motion report output exists')
    policy=json.loads(args.policy.read_text())
    loader=CadDocument.from_index if args.source.suffix=='.npz' else CadDocument.from_step
    with loader(args.source,expected_sha256=policy['source_sha256']) as document:
        result=compile_source_motion(document,policy)
    result.pop('face_owners')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print('Prepared',len(result['selections']),'source motion selections; source unchanged')


if __name__=='__main__':main()
