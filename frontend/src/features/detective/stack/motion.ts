// Motion of the evidence stack, pure: a critically damped spring per slab and the "collapsed" report.

export interface SlabMotion { y: number; v: number }
export interface CollapseState { wasExploded: boolean; reported: boolean }

const STIFF = 90;
const DAMP = 2 * Math.sqrt(STIFF); // critically damped: no bounce past the target
const POS_EPS = 0.0008;
const VEL_EPS = 0.004;

/** One spring step towards `target`; snaps onto it once close and slow. Returns a fresh state. */
export function springStep(m: SlabMotion, target: number, dt: number): SlabMotion {
  const a = STIFF * (target - m.y) - DAMP * m.v;
  const v = m.v + a * dt;
  const y = m.y + v * dt;
  return Math.abs(target - y) <= POS_EPS && Math.abs(v) <= VEL_EPS ? { y: target, v: 0 } : { y, v };
}

export const atRest = (m: SlabMotion, target: number): boolean => m.y === target && m.v === 0;

/**
 * Whether to report "collapsed" this frame. Only after the stack has been exploded at least once, so a stack that
 * starts on the ground (mount, one slab, reduced motion) is never reported collapsed before it opened; and only once.
 */
export function collapseReport(
  s: CollapseState, exploded: boolean, moving: boolean,
): { state: CollapseState; report: boolean } {
  if (exploded) return { state: { wasExploded: true, reported: false }, report: false };
  if (!s.wasExploded || s.reported || moving) return { state: s, report: false };
  return { state: { wasExploded: true, reported: true }, report: true };
}
