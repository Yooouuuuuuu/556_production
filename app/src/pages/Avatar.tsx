import { useEffect, useState } from 'react';
import { api, BASE } from '../api';
import { useStore } from '../store';
import { Live2DStage } from '../live2d/Live2DStage';

// Avatar window: transparent, the companion bottom-center, speech bubble above her head.
export function Avatar() {
  const [modelUrl, setModelUrl] = useState<string | null>(null);
  const { bubble, connect, avatarUrl } = useStore();

  useEffect(() => {
    connect();
    let alive = true;
    const load = async () => {
      try {
        const c = await api.companion();
        if (alive) setModelUrl(BASE + c.avatar_model_url);
      } catch {
        setTimeout(load, 2000); // backend still starting
      }
    };
    load();
    return () => { alive = false; };
  }, []);

  // the avatar follows the chat window: a roster switch changes her model
  useEffect(() => { if (avatarUrl) setModelUrl(avatarUrl); }, [avatarUrl]);

  return (
    <div className="relative w-full h-full select-none">
      {modelUrl && <Live2DStage modelUrl={modelUrl} />}
      {bubble && (
        <div className="absolute left-1/2 top-[5%] -translate-x-1/2 max-w-[78%] px-3.5 py-2 rounded-2xl bg-white text-neutral-800 text-sm leading-relaxed shadow-lg break-words
          after:content-[''] after:absolute after:left-1/2 after:-bottom-2 after:-translate-x-1/2 after:border-8 after:border-transparent after:border-t-white after:border-b-0">
          {bubble.text}
        </div>
      )}
    </div>
  );
}
