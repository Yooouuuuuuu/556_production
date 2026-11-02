import { useEffect, useState } from 'react';
import { Avatar } from './pages/Avatar';
import { Shell } from './pages/Shell';

// Two windows share one bundle: the avatar window (#/avatar, transparent) and the office window (everything else).
// #/settings opens the office with the gear screen up (the tray menu and the avatar's context menu link there).
function useRoute() {
  const read = () => location.hash.replace(/^#\/?/, '') || 'chat';
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return route;
}

export function App() {
  const route = useRoute();
  useEffect(() => { document.body.dataset.route = route === 'avatar' ? 'avatar' : 'office'; }, [route]);
  if (route === 'avatar') return <Avatar />;
  return <Shell initialScreen={route === 'settings' ? 'settings' : 'main'} />;
}
