# SPDX-License-Identifier: MIT OR Apache-2.0
"""Optional demonstration trajectories. No match-mode controller lives here."""
import math


def demo_coordinate(joint, time_s, active_target_mode=None):
    """Return a demo coordinate, or None when another controller owns the joint."""
    profile = joint.get('demo_motion')
    if profile is None or active_target_mode is not None:
        return None
    if profile.get('demo_only') is not True or profile.get('when') != 'no_target_mode':
        raise ValueError('demo motion must explicitly yield to target modes')
    if profile.get('type') != 'sinusoidal' or profile.get('range') != 'joint_limits':
        raise ValueError('unsupported demo trajectory')
    lo, hi = joint['limits']
    period = profile['period_s']
    phase = profile.get('phase_rad', 0)
    if not all(math.isfinite(v) for v in [lo, hi, period, phase, time_s]) or lo > hi or period <= 0:
        raise ValueError('invalid demo trajectory parameters')
    return (lo+hi)/2 + (hi-lo)/2 * math.sin(2*math.pi*time_s/period + phase)
