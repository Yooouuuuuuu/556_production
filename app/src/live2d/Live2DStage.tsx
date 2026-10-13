import { useEffect, useRef } from 'react';
import { BASE } from '../api';
import { useStore } from '../store';

// Live2D stage: pixi + pixi-live2d-display in a transparent canvas. Port of the Artemis viewer's
// essentials: load the model served by 556d, fit it bottom-center, idle motions, tap motions,
// and hub-driven motion events. Cubism Core 4 is fetched from 556d (vendor/live2d) at runtime
// and must be a global before the cubism4 runtime loads.

let corePromise: Promise<void> | null = null;
function loadCore(): Promise<void> {
  if (corePromise) return corePromise;
  corePromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = `${BASE}/live2dcubismcore.min.js`;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('cubism core failed to load'));
    document.head.appendChild(s);
  });
  return corePromise;
}

export function Live2DStage({ modelUrl }: { modelUrl: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const modelRef = useRef<any>(null);
  const motion = useStore((s) => s.motion);

  useEffect(() => {
    let disposed = false;
    let app: any = null;
    (async () => {
      await loadCore();
      const PIXI = await import('pixi.js');
      (window as any).PIXI = PIXI;
      const { Live2DModel } = await import('pixi-live2d-display-lipsyncpatch/cubism4');
      Live2DModel.registerTicker(PIXI.Ticker as any);
      if (disposed || !hostRef.current) return;

      const host = hostRef.current;
      app = new PIXI.Application({
        backgroundAlpha: 0,
        antialias: true,
        autoDensity: true,
        resolution: window.devicePixelRatio || 1,
        resizeTo: host,
      });
      host.appendChild(app.view as HTMLCanvasElement);

      const model: any = await Live2DModel.from(modelUrl, { autoInteract: true });
      if (disposed) { model.destroy(); return; }
      modelRef.current = model;
      model.anchor.set(0.5, 1);
      app.stage.addChild(model);
      const fit = () => {
        const w = host.clientWidth, h = host.clientHeight;
        const natural = model.internalModel.originalHeight || model.height / model.scale.y;
        const scale = (h * 0.96) / natural;
        model.scale.set(scale);
        model.position.set(w / 2, h);
      };
      fit();
      const ro = new ResizeObserver(fit);
      ro.observe(host);
      (model as any)._ro = ro;
    })().catch((e) => console.error('[live2d]', e));

    return () => {
      disposed = true;
      const m = modelRef.current;
      if (m) { (m as any)._ro?.disconnect(); m.destroy(); modelRef.current = null; }
      if (app) { app.destroy(true, { children: true }); }
    };
  }, [modelUrl]);

  // hub → motion (e.g. /api/motion?name=TapBody or emotion events)
  useEffect(() => {
    if (!motion || !modelRef.current) return;
    try { modelRef.current.motion(motion.name); } catch { /* unknown group: ignore */ }
  }, [motion]);

  return <div ref={hostRef} className="w-full h-full" />;
}
