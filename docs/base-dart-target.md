# Base dart-target rail

The target above the base rail is an independent moving group. Its detector,
green guiding light, fittings and raised source details move together. The
rail, end hardware and support beneath it remain fixed.

`base.dart_target.slide` is a prismatic joint along base-local Y with limits
`[-0.280, +0.280]` m. Rulebook V2.1.0 section 5.6.5, printed pages 124–125,
specifies this travel and requires the target and guiding light to retain
their relative positions. The roughly 980 mm rail mesh is longer than the
allowed travel. Its geometric ends are not treated as target centre limits.

The fixed `base.dart_target.rail` node carries rail metadata and a joint
reference. The moving core is `base.dart_target.carriage`; the guiding light
has its own semantic ID and LED channel. Joint children list every moving
source group explicitly. No source triangles or collision were removed.

## Demo only

When no target mode is active, the optional preview uses:

```text
q(t) = 0.280 * sin(2*pi*t/4) metres
```

This visits both allowed extremes and starts at the initial position. The
four-second period is an adjustable demo default, not a rulebook speed. Its
peak speed is approximately 0.440 m/s. `demo_motion` is stored separately
from `rulebook_motion` in the joint metadata.

[`preview/motion_profiles.py`](../python/preview/motion_profiles.py) implements
this optional trajectory. `demo_coordinate(joint, time_s, active_target_mode)`
returns `None` whenever a target mode is supplied, so the demo yields control.
The exporter writes static geometry, joints and metadata; it does not run a
match controller, enable target modes, or modify the simulator.

## Rules recorded for future simulation

The exported metadata records four modes without implementing their controller:

- Fixed target stays at the initial position.
- Random fixed target changes position before the gate fully opens, changes
  again on a hit, and returns when the detection window ends.
- Random moving target starts with gate opening. On launch detection it moves
  to a different position and stops within 600 ms.
- Terminal moving target waits 1.2 seconds after launch detection before that
  repositioning move, which then finishes within 600 ms.

The rulebook also describes resuming motion on a hit or ten seconds after the
first detected launch in the window. It does not specify a constant cruising
speed. Those event semantics belong to a future simulator controller and do
not change the standalone sine-wave demo.

The integration check verifies both travel limits, fixed rail transforms,
constant detector/light relative pose, and containment of the complete moving
carriage within the rail's span. The updated [base GIF](previews/base-joints.gif)
shows the rail demo alongside the illustrative shield opening.
