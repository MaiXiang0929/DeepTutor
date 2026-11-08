import { useEffect, useState } from "react";
import { Canvas, Circle, RoundedRect } from "@shopify/react-native-skia";

export function SynthesisCanvas({run}: {run: number}) {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    if (!run) return;
    let frame = 0;
    const started = Date.now();
    function draw() {
      const fraction = Math.min(1, (Date.now() - started) / 760);
      setProgress(fraction);
      if (fraction < 1) frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [run]);
  return <Canvas style={{width: 270, height: 125}}>
    <Circle cx={135} cy={62} r={46} color="#302859" />
    {Array.from({length: 12}, (_, i) => {
      const angle = i * Math.PI / 6 + progress * Math.PI;
      const radius = 50 * (1 - progress);
      return <Circle key={i} cx={135 + Math.cos(angle) * radius} cy={62 + Math.sin(angle) * radius} r={3} color="#a5b4fc" />;
    })}
    {run > 0 && <RoundedRect x={135 - 21 * Math.abs(Math.cos(progress * Math.PI))} y={29}
      width={42 * Math.abs(Math.cos(progress * Math.PI))} height={66} r={9} color="#e9d5ff" />}
  </Canvas>;
}
