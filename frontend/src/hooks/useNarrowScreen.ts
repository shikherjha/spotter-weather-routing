import { useEffect, useState } from "react";

// Below this width (phones and portrait tablets) the map can't share the screen with floating panels,
// so the layout stacks instead.
const NARROW = "(max-width: 1023px)";

export function useNarrowScreen(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW).matches);
  useEffect(() => {
    const m = window.matchMedia(NARROW);
    const update = () => setNarrow(m.matches);
    m.addEventListener("change", update);
    return () => m.removeEventListener("change", update);
  }, []);
  return narrow;
}
