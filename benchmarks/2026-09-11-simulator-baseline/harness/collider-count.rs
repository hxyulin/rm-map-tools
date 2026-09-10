// SPDX-License-Identifier: LicenseRef-Proprietary
use rm_simulator_server::{cad_assets,layout::*};
use rm_simulator_world::*;
fn main()->anyhow::Result<()> {
let cad=cad_assets::load(std::path::Path::new("/Users/hxyulin/dev/RM/assets/rm2026-field"))?;
let t=load_terrain(&cad)?;
let mut f=Field::new(&field_config(&cad,&LayoutOptions{rune:Some(RuneKind::Small),outpost_speed_rad_s:outpost::DEFAULT_SPEED_RAD_S,terrain:true,referee:true}))?;
add_terrain(&mut f,&t)?;let(v,i)=f.static_geometry();println!("ACTUAL_STATIC vertices={} triangles={}",v.len(),i.len());Ok(())
}
