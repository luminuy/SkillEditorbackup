# clipstudio engine — CLI reference

Run everything from the repo root. Every project lives in `projects/<slug>/`.

| Command | What it does | Writes |
|---|---|---|
| `doctor` | checks ffmpeg filters (ass, loudnorm, silencedetect, sidechaincompress, afftdn), faster-whisper, pythainlp, Pillow, fonts, config | — |
| `init VIDEO [--name SLUG]` | probes the video (size, fps, rotation, audio) | `project.json` |
| `transcribe SLUG [--model M] [--lang th] [--srt F] [--backend auto|faster|mlx] [--resync]` | faster-whisper with word timestamps + VAD + niche vocabulary prompt; Thai words re-segmented with pythainlp; auto-fixes from preset `asr.fixes` | `transcript.json/.txt/.srt`, `audio16k.wav` |
| `fix SLUG ID "text" [ID "text" …]` | replace a segment's text, keep its timing, redistribute word timings | updates transcript |
| `analyze SLUG` | silences, chapters (zodiac / weekday / pile / custom regex), scored candidate windows, risk flags | `silences.json`, `analysis.json`, `analysis.md` |
| `frames SLUG [--times a,b] [--every S] [--count N] [--video F] [--tag T]` | labelled contact sheet so an agent can *look* at the footage (Read the jpg) | `work/frames_<tag>.jpg` |
| `find SLUG "text"` | exact source time of a word/phrase (for `labels.at`, `fx.at`, segment starts) | — |
| `plan-check SLUG` | validates plan: durations per platform (after silence cut + transitions), hook length, card ids, styles/transitions/fx names, speed; prints fx/sfx counts; exit 1 on ERROR | — |
| `capcut SLUG [--clip ID] [--raw] [--zip]` | CapCut kit: text-free video (effects baked, or none with --raw), .srt (lines + words), transparent full-frame PNG overlays, sfx + cue csv, markers.csv, EDIT_GUIDE.md | `capcut/<id>/` |
| `sfx` | list / synthesise the sound-effect library | `assets/sfx/*.wav` |
| `nle SLUG [--clip ID]` | Final Cut Pro / Resolve FCPXML (cuts reference the original media + markers + PNG overlays), Premiere EDL, SRT, markers csv | `nle/` |
| `render SLUG [--clip ID]… [--draft]` | renders clips (draft = ultrafast, CRF 28) | `renders/<id>[.draft].mp4`, `renders/manifest.json`, `work/<id>.ass` |
| `snapshot SLUG CLIP` | 5-frame sheet of a render (0.6 s, 25/50/75 %, last second) | `work/snap_<id>.jpg` |
| `thumbnail SLUG --time T --title "…" [--sub "…"] [--size 1080x1920] [--clip ID] [--x 0.5] [--video F]` | frame + glow title + badge + watermark | `thumbs/<clip>_<size>.jpg` |
| `qa SLUG [--clip ID]…` | resolution/codec/fps, duration vs platform limits, loudness & true peak, dead air at start, hook present, copy limits, risky wording | `qa.json`, `qa.md` (exit 1 on fail) |
| `review SLUG [--start YYYY-MM-DD]` | gallery page + posting schedule + copy-paste caption files | `review.html`, `schedule.csv`, `publish/<id>/<platform>.txt` |
| `cards [--search Q] [--id ID] [--json]` | tarot card lookup (Thai + English, aliases) | — |
| `status SLUG` | which pipeline steps are done | — |

## plan.json (written by clip-story-producer)

```jsonc
{
  "project": "<slug>",
  "clips": [{
    "id": "01-aries",                      // unique, used for file names; order = posting order
    "title": "ราศีเมษ ความรักรายสัปดาห์",   // internal name (review page)
    "format": "vertical",                   // vertical 1080x1920 | portrait 1080x1350 | square | horizontal 1920x1080
    "segments": [                           // SOURCE seconds; several = montage
      {"start": 19.0, "end": 46.5},
      {"start": 60.2, "end": 71.0, "zoom": 1.15, "x": 0.45, "transition_in": "crossfade"}   // per-segment reframe / incoming transition
    ],
    "sort": true,                           // false = keep segment order (cold open: put the reveal first)
    "reframe": {"mode": "fit", "bg": "blur"},   // fit (+bg blur|#hex, zoom, fg_y) | crop (+x, y, zoom) | stack (+regions)
    "hook": "ราศีเมษ คนที่คิดถึงกำลังจะทักมา",   // on-screen title; ≤ ~40 Thai chars; no emoji
    "hook_seconds": null,                   // null = whole clip, or e.g. 4
    "labels": [                             // lower-third badges at SOURCE time
      {"at": 22.6, "card": "the-lovers", "reversed": false, "duration": 3},
      {"at": 30.0, "text": "กอง 1", "duration": 2.5}
    ],
    "captions": {"style": "highlight", "lines": 1},   // or false; style: highlight|karaoke|pop|plain
    "cta": null,                            // null = config default, "" / false = none, or custom text
    "remove_silence": true,
    "speed": 1.0,                           // 1.05–1.12 tightens slow talkers; never > 1.15
    "music": null,                          // path to a licensed track (assets/music/…); ducked under voice
    "music_volume": 0.12,
    "voice_enhance": true,
    "disclaimer": false,                    // burn a small disclaimer for the first seconds
    "notes": "why this clip works",         // for humans / QA
    "kind": "zodiac",                       // zodiac | pile | weekday | message | highlight → picks CTA from cta_by_kind
    "platforms": ["tiktok", "shorts"],      // optional; default = channel.config.json platforms

    // ---- effects & pacing (skill clip-effects) ----
    "style": "dynamic",                     // none | calm | dynamic | viral
    "transition": "zoom",                   // between segments: crossfade dissolve zoom whip slide blur circle dip flashfade … | cut punch flash shake glitchcut
    "fx": [{"at": 95.5, "type": "stars", "duration": 1.6, "sfx": "shimmer"}],   // punch zoom shake glitch flash flash-strong sparkle stars glow
    "sfx": [{"at": 70.8, "name": "riser", "offset": -1.2}],                   // whoosh whoosh-soft chime sparkle pop impact riser shimmer click
    "emphasis": ["เนื้อคู่"],                 // extra keywords coloured in captions
    "caption_anim": "pop",                  // none | fade | pop | bounce
    "auto_fx": true, "sfx_enabled": true, "sfx_map": {"reveal": "chime"}, "cut_punch": 0.08, "vignette": true,

    // ---- finishing (pro) ----
    "look": "mystic", "lut": null, "sharpen": 0.4, "denoise": false,   // none clean warm mystic moody vibrant
    "remove_fillers": true, "fps": "source"                             // captions.style may also be "bold" (+ max_words)
  }]
}
```

### Reframe modes
- **fit** (default, safest): whole 16:9 frame centred over a blurred copy of itself. Captions sit on the blurred area below the picture. `zoom` 1.2–1.6 crops the sides to make the picture bigger; `fg_y` moves the picture up/down (0.5 = centre, 0.42 = a bit higher to leave room for captions).
- **crop**: fills the 9:16 frame from the source; `x`/`y` pick the centre (0–1). Use when the subject (face or the card spread) is in one area. Check with `frames` first.
- **stack**: two or more regions of the source stacked vertically — e.g. reader's face on top, card spread below. `regions: [{"x":0.3,"y":0,"w":0.4,"h":0.6},{"x":0,"y":0.5,"w":1,"h":0.5,"weight":1.3}]` (fractions of source; weight = share of height).

### Safe zones (1080x1920)
Top ~10 % (status bar, tabs) and bottom ~20 % (caption, music, buttons) and a right strip ~12 % (like/comment/share buttons) are covered by app UI. Defaults: hook at y 0.15, labels 0.29, captions 0.68, CTA centre 0.44, watermark top-left 0.105. Change positions in `channel.config.json`, not per clip.

## Config (`channel.config.json` → merged over `presets/<preset>.json` → over engine defaults)
Brand colours (`brand.primary/accent/text/outline/hook_box`), fonts (bundled Kanit Regular/Bold/ExtraBold — any font dropped into `assets/fonts` works by family name), caption style/size/position, hook/label/CTA/watermark/progress bar, disclaimer, audio targets (-14 LUFS, -1.5 dBTP), silence-cut thresholds, platforms, posting slots, ASR model/prompt/fixes, `chapter_patterns` (custom regex chapters: `[{"pattern":"ตอนที่\\s*\\d+","kind":"episode","label":"ตอน"}]`).
