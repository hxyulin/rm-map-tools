"""Stage a generic ignored CCD test temporarily, run via Nix/mbx, then clean up."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BENCH=Path(__file__).resolve().parent;OUT=ROOT/'out/rmuc2027-dart-beams-refined';WORKTREE=ROOT.parent/'rm-simulator-native-collisions'
source=BENCH/'mesh_ccd.rs';target=WORKTREE/'crates/rm-sim-physics/tests/dart_side_profile_trial.rs'
assert not target.exists(),'Refusing to overwrite an existing test file'
subprocess.run(['nix','develop','--command','rustfmt','--edition','2024',str(source)],cwd=WORKTREE,check=True)
payload=source.read_bytes();target.write_bytes(payload);environment=os.environ.copy();environment['RM_DART_CCD_FIXTURE_TXT']=str(OUT/'mesh-ccd-fixture.txt')
command=['nix','develop','--command',str(Path.home()/'.cargo/bin/mbx'),'test','-p','rm-sim-physics','--locked','--test','dart_side_profile_trial','--','--ignored','--nocapture']
status=-1
try:
 with (OUT/'mesh-ccd.log').open('w')as log:
  process=subprocess.Popen(command,cwd=WORKTREE,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  for line in process.stdout:print(line,end='',flush=True);log.write(line);log.flush()
  status=process.wait()
finally:
 if target.exists()and hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(payload).digest():target.unlink()
proof=dict(command=command,worktree=str(WORKTREE),exit_code=status,fixture_sha256=hashlib.sha256((OUT/'mesh-ccd-fixture.txt').read_bytes()).hexdigest(),test_source_sha256=hashlib.sha256(payload).hexdigest(),temporary_test_removed=not target.exists(),scope='WorldPhysics CCD test of generated profile triangle meshes; no field installation or full-match integration.')
(OUT/'mesh-ccd-result.json').write_text(json.dumps(proof,indent=2)+'\n')
raise SystemExit(status)
