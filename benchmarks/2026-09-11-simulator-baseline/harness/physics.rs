// SPDX-License-Identifier: LicenseRef-Proprietary
use rm_simulator_server::{cad_assets,layout::*};
use rm_simulator_world::*;
use std::time::Instant;
fn main()->anyhow::Result<()> {
 let start=Instant::now();let cad=cad_assets::load(std::path::Path::new("/Users/hxyulin/dev/RM/assets/rm2026-field"))?;println!("manifest_load_ms {}",start.elapsed().as_secs_f64()*1000.0);
 let start=Instant::now();let terrain=load_terrain(&cad)?;println!("terrain_load_ms {}",start.elapsed().as_secs_f64()*1000.0);
 println!("{}",terrain.describe());println!("ground_triangles {} fixtures_triangles {} equipment_triangles {}",terrain.ground.triangles.len(),terrain.fixtures.triangles.len(),terrain.equipment.iter().map(|m|m.triangles.len()).sum::<usize>());
 for collision in [true,false] {for (scenario,count,shoot) in [("empty",0,false),("one_idle",1,false),("one_drive_fire",1,true),("14_drive_fire",14,true)] {for repeat in 0..3 {
 let mut field=Field::new(&field_config(&cad,&LayoutOptions{rune:Some(RuneKind::Small),outpost_speed_rad_s:outpost::DEFAULT_SPEED_RAD_S,terrain:collision,referee:true}))?;
 let start=Instant::now();if collision {add_terrain(&mut field,&terrain)?;}let build_ms=start.elapsed().as_secs_f64()*1000.0;
 let mut ids=Vec::new();
 for i in 0..count {let team=if i%2==0 {Team::Red}else{Team::Blue};let (mut spawn,yaw)=default_spawn(team);spawn[1]+=(i/2) as f64*0.8;ids.push(field.add_chassis(&chassis_placement(ChassisConfig::default(),if collision {Some(&terrain)}else{None},team,spawn,yaw))?);}
 field.step(2000)?;
 let mut times=Vec::new();
 for i in 0..10000 {if shoot {for &id in &ids {field.command_chassis(id,ChassisCommand{forward_m_s:1.0,left_m_s:0.0,yaw_rate_rad_s:0.25,..Default::default()})?;}if i%100==0 {let snapshot=field.snapshot();for c in &snapshot.chassis {let mut muzzle=c.pose;muzzle.translation_m[2]+=0.5;field.fire(muzzle,Shot::at_limit(Caliber::Mm17),Some(c.id))?;}}}
 let start=Instant::now();field.step(1)?;times.push(start.elapsed().as_secs_f64()*1000.0);}
 times.sort_by(f64::total_cmp);println!("PHYSICS {}",serde_json::json!({"collision":collision,"scenario":scenario,"repeat":repeat,"build_ms":build_ms,"ticks":times.len(),"mean_ms":times.iter().sum::<f64>()/times.len() as f64,"p50_ms":times[5000],"p95_ms":times[9500],"p99_ms":times[9900],"max_ms":times[9999],"shots_fired":field.snapshot().shots_fired}));
 }}}
 Ok(())
}
