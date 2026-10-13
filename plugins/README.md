# plugins/ — our Python that plugs INTO Hermes

Hermes extension points are Python by contract (memory providers, platform adapters, skills).
Source lives here; setup copies each plugin into `home/plugins/` (Hermes's drop-in location) so
`vendor/hermes-agent` stays pristine. Planned: `kokoro/` (Path C memory provider), a platform
adapter for proactive pushes to 556d.
