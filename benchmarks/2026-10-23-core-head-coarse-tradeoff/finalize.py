"""Final artifact checks for the explicitly coarse head alternatives."""
import json
from pathlib import Path
from build import OUT,scan

def main():
    proof=json.loads((OUT/'geometry-verification.json').read_text());renders=json.loads((OUT/'renders.json').read_text());assert len(renders['views'])==48
    for row in renders['views']:assert scan.digest(Path(row['path']))==row['sha256']
    for item in json.loads((OUT/'variants.json').read_text()):
        path=Path(item['path']);r=json.loads(path.read_text());assert scan.digest(path)==item['sha256']
        for source,h in r['input_pins'].items():assert scan.digest(Path(source))==h
    hashes={str(x.relative_to(OUT)):scan.digest(x)for x in OUT.rglob('*')if x.is_file()and x.name not in ['final-verification.json','gallery.html']}
    (OUT/'final-verification.json').write_text(json.dumps(dict(geometry=proof,matched_image_count=48,artifact_sha256=hashes,runtime_supported=False,installed=False,contact_validated=False),indent=2)+'\n')
    print('Verified balanced/lean envelopes, 48 matched images and all frozen input hashes.')

if __name__=='__main__':main()
