/** Decorative geometry only. These coordinates never represent knowledge records. */
export const ARCHIVE_FACE = { width:3.2, height:1.6, depth:.42 }
export const HELIX_RADIUS = 5.1
export function helixPoint(y:number, strand:number, time:number): [number,number,number] {
  const angle=y*.34+strand*Math.PI
  const radius=HELIX_RADIUS+.14*Math.sin(y*.52-time*.65)
  return [Math.cos(angle)*radius,y,Math.sin(angle)*radius]
}
