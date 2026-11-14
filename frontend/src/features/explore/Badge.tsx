import { Stamp } from "../../lib/Stamp";
import type { Direction, Verdict } from "./types";

export default function Badge({ verdict, direction }: { verdict: Verdict; direction: Direction }) {
  return <Stamp verdict={verdict} direction={direction} />;
}
