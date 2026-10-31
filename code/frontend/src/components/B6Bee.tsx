import { useCallback, useEffect, useRef, useState } from "react";

// Team B6 easter egg: the whiteboard bee crosses the bottom of the screen and drops six little 6s.
// It flies once after a minute of idling, or when someone clicks the sleepy bee in the footer.
const FLIGHT_MS = 7000;
const IDLE_MS = 60000;

type Six = { id: number; x: number; y: number };

export default function B6Bee() {
  const [flying, setFlying] = useState(false);
  const [sixes, setSixes] = useState<Six[]>([]);
  const bee = useRef<HTMLImageElement>(null);
  const reducedMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const fly = useCallback(() => {
    if (!reducedMotion) setFlying(true);
  }, [reducedMotion]);

  // Drop one 6 behind the bee every ~1/7 of the flight: six in total.
  useEffect(() => {
    if (!flying) return;
    let dropped = 0;
    const drop = setInterval(() => {
      const box = bee.current?.getBoundingClientRect();
      if (box && dropped < 6) {
        dropped += 1;
        setSixes((s) => [...s, { id: Date.now() + dropped, x: box.left + 6, y: box.top + box.height * 0.6 }]);
      }
    }, FLIGHT_MS / 7);
    const land = setTimeout(() => setFlying(false), FLIGHT_MS);
    const clear = setTimeout(() => setSixes([]), FLIGHT_MS + 2500);
    return () => {
      clearInterval(drop);
      clearTimeout(land);
      clearTimeout(clear);
    };
  }, [flying]);

  // One idle flight per visit.
  useEffect(() => {
    const events = ["pointerdown", "keydown", "scroll"] as const;
    const stop = () => events.forEach((e) => window.removeEventListener(e, reset));
    const idleFlight = () => {
      stop();
      fly();
    };
    let timer = setTimeout(idleFlight, IDLE_MS);
    function reset() {
      clearTimeout(timer);
      timer = setTimeout(idleFlight, IDLE_MS);
    }
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    return () => {
      clearTimeout(timer);
      stop();
    };
  }, [fly]);

  return (
    <>
      <footer className="footer">
        <span>Adobee Hive · BaselHack 2026 · Team B</span>
        <button className="b6-perch" onClick={fly} aria-label="Wake the B6 bee" title="6">
          <img src="/brand/mascot.svg" alt="" className={flying ? "away" : ""} />
        </button>
      </footer>
      {flying && (
        <div className="b6-flight" style={{ animationDuration: `${FLIGHT_MS}ms` }} aria-hidden>
          <img ref={bee} src="/brand/mascot.svg" alt="" className="b6-bob" />
        </div>
      )}
      {sixes.map((s) => (
        <span key={s.id} className="b6-six" style={{ left: s.x, top: s.y }} aria-hidden>
          6
        </span>
      ))}
    </>
  );
}
