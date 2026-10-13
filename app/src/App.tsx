import { useEffect, useState } from 'react';
import { Office } from './pages/Office';
import { Avatar } from './pages/Avatar';

// Hash routing: the office window opens #/office, the avatar window #/avatar.
function useRoute(): string {
  const read = () => (window.location.hash.replace(/^#\/?/, '') || 'office');
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
  const tab = route === 'settings' ? 'settings' : route === 'memory' ? 'memory' : route === 'roster' ? 'roster' : 'chat';
  return <Office initialTab={tab} />;
}
