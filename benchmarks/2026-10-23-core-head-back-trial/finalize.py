"""Verify image/stage hashes after geometry checks and matched rendering."""
import json
from pathlib import Path
from survey import OUT,p

def main():
    geometry=json.loads((OUT/'geometry-verification.json').read_text());renders=json.loads((OUT/'renders.json').read_text())
    assert len(renders['views'])==72
    for row in renders['views']:assert p.scan.digest(Path(row['path']))==row['sha256']
    for variant in json.loads((OUT/'variants.json').read_text()):
        path=Path(variant['path']);r=json.loads(path.read_text());assert p.scan.digest(path)==variant['sha256']
        for source,h in r['input_pins'].items():assert p.scan.digest(Path(source))==h
        stage=json.loads((path.parent/'paired-stage.json').read_text())
        for role in ['visual','collision']:
            assert sum(v['placed_triangles']for v in stage[f'{role}_assets'].values())==stage[f'placed_{role}_triangles']
            for v in stage[f'{role}_assets'].values():assert p.scan.digest(Path(v['path']))==v['sha256']
        assert stage['placed_collision_triangles']==r['field_preview_triangles']
        assert stage['placed_collision_triangles']-39*96*2==r['field_native_mesh_triangles']
    artifacts={str(x.relative_to(OUT)):p.scan.digest(x)for x in OUT.rglob('*')if x.is_file()and x.name not in ['final-verification.json','gallery.html']}
    output=dict(geometry=geometry,matched_image_count=72,stage_counts_and_all_inputs_exact=True,artifact_sha256=artifacts,installed=False,contact_validated=False)
    (OUT/'final-verification.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Verified two head trials, 72 image hashes, complete stage counts and unchanged inputs.')

if __name__=='__main__':main()
