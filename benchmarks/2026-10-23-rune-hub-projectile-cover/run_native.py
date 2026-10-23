"""Stage a generic ignored CCD test temporarily, run via Nix/mbx, then clean up."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BENCH=Path(__file__).resolve().parent;OUT=ROOT/'out/rmuc2027-rune-hub-projectile-cover';WORKTREE=ROOT.parent/'rm-simulator-native-collisions'
source=BENCH/'native_ccd.rs';target=WORKTREE/'crates/rm-sim-physics/tests/native_rune_hub_cover_trial.rs'
assert not target.exists(),'Refusing to overwrite an existing test file'
subprocess.run(['nix','develop','--command','rustfmt','--edition','2024',str(source)],cwd=WORKTREE,check=True)
payload=source.read_bytes();target.write_bytes(payload);environment=os.environ.copy();environment['RM_HUB_CCD_FIXTURE_TXT']=str(OUT/'native-ccd-fixture.txt')
command=['nix','develop','--command',str(Path.home()/'.cargo/bin/mbx'),'test','-p','rm-sim-physics','--locked','--test','native_rune_hub_cover_trial','--','--ignored','--nocapture']
status=-1
try:
 with (OUT/'native-ccd.log').open('w')as log:
  process=subprocess.Popen(command,cwd=WORKTREE,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  for line in process.stdout:print(line,end='',flush=True);log.write(line);log.flush()
  status=process.wait()
finally:
 if target.exists()and hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(payload).digest():target.unlink()
proof=dict(command=command,worktree=str(WORKTREE),exit_code=status,fixture_sha256=hashlib.sha256((OUT/'native-ccd-fixture.txt').read_bytes()).hexdigest(),test_source_sha256=hashlib.sha256(payload).hexdigest(),temporary_test_removed=not target.exists(),scope='Native WorldPhysics CCD test of generated convex hulls; field mixed-shape loader and full match integration not exercised.')
(OUT/'native-ccd-result.json').write_text(json.dumps(proof,indent=2)+'\n')
raise SystemExit(status)
