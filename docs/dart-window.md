# Dart sliding window

Rulebook V2.1.0 Figures 4-14 and 4-15 show the window raised above the launch
opening. Figure 4-16 places the gliding-platform surface 205 mm above the floor.
The window and the horizontally extending platform are separate mechanisms.

The source window and its carriage already have an exact triangle partition.
The two lower guide rails remain fixed. Their measured long axis agrees with
`[sin(15 degrees), 0, cos(15 degrees)]` in the asset frame. Opening raises the
window along that inclined axis; closing follows it downward.

The corrected illustrative lower stop places the lowest carriage point at
205 mm instead of 79.9 mm. The latter passed below the platform level. This
produces approximately 1.16448 m of travel from the source open pose. It is
inferred from the figure, not a measured actuator stop. The separate platform
remains fixed pending its own verified mesh partition and joint binding.

The integration verifier checks the lower height, unchanged guide/platform
transforms, and preservation of every source triangle and material.

[Clean orbit](previews/clean/dart-station-joints-orbit.mp4) ·
[Fixed-camera inspection](previews/dart-station-joints.mp4)
