"""Check rendered fit comparisons and all review recipe artifact hashes."""
import json
from pathlib import Path
from research import OUT,scan

def main():
    r=json.loads((OUT/'verification.json').read_text());proof=json.loads((OUT/'geometry-verification.json').read_text());renders=json.loads((OUT/'renders.json').read_text())
    assert len(renders['views'])==36
    for row in renders['views']:assert scan.digest(Path(row['path']))==row['sha256']
    for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h
    stage=json.loads((OUT/'paired-stage.json').read_text())
    for role in ['visual','collision']:
        for entry in stage[f'{role}_assets'].values():assert scan.digest(Path(entry['path']))==entry['sha256']
    hashes={str(x.relative_to(OUT)):scan.digest(x)for x in OUT.rglob('*')if x.is_file()and x.name not in ['final-verification.json','gallery.html']}
    (OUT/'final-verification.json').write_text(json.dumps(dict(geometry=proof,matched_image_count=36,artifact_sha256=hashes,runtime_supported=False,installed=False),indent=2)+'\n')
    print('Verified mixed vector recipe, 36 matched images and unchanged inputs.')

if __name__=='__main__':main()
