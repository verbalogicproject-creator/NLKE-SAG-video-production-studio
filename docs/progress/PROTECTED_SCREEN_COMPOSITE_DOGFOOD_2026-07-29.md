# Protected screen composite dogfood — 2026-07-29

## Result

The first-class protected-screen-composite workflow passed a real local Studio
dogfood run. The run used the refined Omni plate and deterministic SIFT/RANSAC
composite produced on July 28; it did not dispatch another paid generation.

The browser-visible control project is `SAG Protected Composite Dogfood` and its
vertical sequence is `SAG Protected Composite 9x16`. The engine project reached
revision 6 after the exact-revision Studio insertion.

## Evidence lineage

| Evidence | SHA-256 |
|---|---|
| Original Android screenshot | `d2f31a37875753aabcb73904788a22d6b9009947583124be7d29ba58094dc709` |
| Canonical managed screenshot | `241c19af7c65d3ce29e41f3ffc37a4728b7fefdc85629c4fd17575a23395d475` |
| Refined Omni plate | `5b4b8d2e00654eef89f524e82e5e7e444e95b5ec66c17150e1a4918f080eda92` |
| Protected composite input | `f4af43b8e51fbb8b6709d4be350769c96679ae16b05b37ec10c4c34568a07fb1` |
| Tracking report | `9cc6b98792ef23524133b159c8bd6db32815f2477cb44053d863d4eeaef982f4` |

The screenshot was bound to immutable recipe
`screenshot_recipe_86c83a23c91e46c2` and approved through the Studio decision
route. Protected composite `protected_composite_2f4790ea6888444f` recorded the
crop `(0, 220, 1116, 2260)`, 144/144 directly tracked frames, no interpolation,
minimum 124 RANSAC inliers, minimum 0.586 inlier ratio, and no untracked gap.

The composite was approved at project revision 5. Studio then created and
consumed an exact confirmation before committing
`timeline.insert_protected_composite` as receipt
`receipt_a83ea9f815124492`, producing revision 6.

## Verified render

- Render receipt: `receipt_68c6280e9d394393`
- Artifact: `artifact_6e65381cbcf94466`
- Downloaded artifact SHA-256:
  `36b0b239610ef2331899eb4a231043c1c811fd05ccc7b8bf51934b4431e73d35`
- Contract: `sag-render-0.3`
- Output: 1080x1920, 30 fps, 6.000 seconds, H.264, no audio
- Receipt state: `observed_success`
- QC state: passed
- Protected-lineage QC: passed with one approved source/plate/output/tracking
  lineage record

The artifact and JSON receipt were downloaded through the same authenticated,
sequence-bound Studio routes used by the Deliver UI. The downloaded MP4 hash
matched the receipt exactly.

Local ignored evidence is retained under
`.sag-video/protected-dogfood-2026-07-29/`. Android opened the real Studio page.
The user then captured the following independent browser-visible evidence under
`/storage/emulated/0/Download/screenshots/sag-video/july 29/`:

| Screenshot | SHA-256 | Observable state |
|---|---|---|
| `Screenshot_20260729_044110.jpg` | `2fd28b4547fadc4084fee611a70dec04104e08308fa2fd49f62d92652df9a7d4` | Runtime connected at verified revision 6; Video and Receipt downloads visible; one approved authentic screenshot and one active protected composite |
| `Screenshot_20260729_044226.jpg` | `94e9e98f8afd74185abe20c410478b524e46f53ab1ad09ad881ae17410ea10ac` | Studio media bin contains the canonical screenshot, refined Omni plate, and managed protected composite |
| `Screenshot_20260729_044325.jpg` | `2ca8bd1b6da6ffe16a2078dfe522d2d221e91ceaba2e4b8716657a79d6e16fdc` | Six-second composite is loaded in the Studio preview |
| `Screenshot_20260729_044329.jpg` | `d828de0136753b9ebfa3c124686f735894ccd751fdc46a109123e2f0ef71761b` | `omni.protected-composite` appears as the active six-second item on the Video track |

These manual screenshots close the browser-visible evidence gap left by the
unavailable Termux system screenshot command.

## Boundary and next gate

This proves the protected visual primitive and Studio governance path. The
output is intentionally silent because composite video cannot own narration or
music. It is not the final 30-second `repo-to-video-1` production.

The next production milestone is the full 30-second assembly: several short
cinematic plates, protected authentic UI regions, local Kokoro narration,
license-receipted music, captions, semantic audio mixing, and final
intelligibility/loudness/human-playback gates.
