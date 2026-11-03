# Third-party code and data

556 Production's own code is MIT (`LICENSE`). These pieces are not ours and keep their own terms; the full table of
dependencies is in `docs/STACK.md` (Third-party).

| Piece | Where | License / terms |
|---|---|---|
| Hermes Agent (Nous Research) | `vendor/hermes-agent/` (git submodule, never edited) | MIT — `vendor/hermes-agent/LICENSE` |
| KeepsakeDB | `vendor/keepsakedb/` (git submodule) | MIT — `vendor/keepsakedb/LICENSE` |
| Live2D Cubism Core | `vendor/live2d/live2dcubismcore.min.js` | Live2D Proprietary Software License Agreement (redistributable code): https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html |
| Hiyori sample model | `assets/live2d/hiyori/` | Live2D Free Material License Agreement: https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html |
| npm, Go and Python packages | restored by their package managers | MIT, ISC, BSD-2/3 — see `docs/STACK.md` |

The Live2D terms are not open-source licenses. Using the Cubism Core or the sample in a published product can require
accepting Live2D's agreements (and, above their revenue threshold, a Cubism SDK release license); check the current
terms on live2d.com before you ship. The rest of 556 runs without them: the avatar window is optional.
