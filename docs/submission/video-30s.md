# 30-second demo video — shot-by-shot script

**Hard limit: 30.0 seconds.** NASA: *"Video (30 seconds or less)"*, and *"Projects that exceed these limits will not be
eligible for Global Judging."* We edit to **29.5 s** so no player rounds 30.4 up into a disqualification.

**Language:** English voice-over, English captions burned in. Mandatory either way — the rule requires English
subtitles only if the audio is not English, but captions protect us if audio fails on the judge's machine.

**Disclosures:** screen capture only, no AI-generated imagery, no NASA logos anywhere on screen, no minors, no
third-party music (the T&Cs require that we hold the rights to every element).

**Fill before recording:** `[TEAM NAME]`, `[LIVE_URL]`, `[org]` in the GitHub URL.

---

## The script

| Time | Picture — what the camera sees | On-screen text | Voice-over | Notes |
|---|---|---|---|---|
| **0.0–3.0** | Lake Mead case, 3D terrain, strong oblique angle. Timeline scrubs 2003 → 2024 in one continuous move; the annual anomaly texture over the basin deepens from neutral to deep red as storage falls. | `Lake Mead, 2003 → 2024` (top left, small) then `Is it the climate — or is it us?` (centre, appears at 0:01) | "This reservoir has been shrinking for twenty years." | Open on motion, not on a logo or a title card. The first frame must already be the product. |
| **3.0–8.0** | Hard cut to the verdict panel. Two rows highlight in sequence: `Total water storage ↓ Real change`, then `Rainfall — Can't tell yet`. Cursor moves once, deliberately. | `Rainfall: no clear trend` then `So what is draining it?` | "Rainfall shows no trend. So what is draining it?" | This is the whole argument of the project in five seconds. Do not rush the cut; let the two labels be readable. |
| **8.0–14.0** | Pull back to the globe / explore map. A click lands on a coastal city. The sweep runs: a column of variable names resolves one by one into verdict chips. Team lower-third appears. | `Earth Trend Detective` + one-line tagline `What is changing here — and is it real?` · lower third: `[TEAM NAME] · Málaga, Spain` | "Earth Trend Detective: pick any place, and we test every NASA variable that applies." | The lower third covers NASA's "introduce yourself and your team" beat without spending voice-over time on it. |
| **14.0–21.0** | Split screen. Left: the variable's time series with the Sen slope drawn. Right: the residual panel with the share climate does not explain. One annotation arrow draws to the residual. | `Climate explains part of it.` → `The rest is the lead.` | "Then we remove what the climate explains. What is left is the part it does not." | Both panels must be legible at 720p. Zoom the UI to 125 % before recording. |
| **21.0–26.0** | The explanation paragraph types in under its label. Then the validator line flashes green: `12 figures checked · 0 mismatches`. | `Written by a language model.` / `Every figure checked against the data.` | "A language model writes it. A validator checks every number." | This is the answer to "another LLM wrapper". Show the check, not the claim. |
| **26.0–30.0** | Cut back to the full 3D scene, slow pull-back, verdict chip still on screen. End card over the terrain. | `Pick a place.` / `[LIVE_URL]` + `github.com/[org]/earth-trend-detective` | "Pick a place. Find out what is really changing." | Hold the end card for at least 1.5 s. No fade to black before 29.5 s. |

**Voice-over total: 66 words in 30 seconds (2.2 words/second).** That is a calm, readable pace. If a take runs long,
**cut words — never speed up the read.** A rushed 30 seconds reads as panic; a calm 29 seconds reads as confidence.

---

## Voice-over only (teleprompter copy)

> This reservoir has been shrinking for twenty years.
>
> Rainfall shows no trend. So what is draining it?
>
> Earth Trend Detective: pick any place, and we test every NASA variable that applies.
>
> Then we remove what the climate explains. What is left is the part it does not.
>
> A language model writes it. A validator checks every number.
>
> Pick a place. Find out what is really changing.

---

## Setup before you hit record

1. **Data loaded and cached.** Do not record against a live API. Run the three cases once, then record from cache.
2. **Window at 1920×1080, browser zoom 125 %**, dark UI, no bookmarks bar, no OS notifications.
3. **Cursor visible only when it does something.** Hide it during the 3D scrub; show it for the map click.
4. **No personal data on screen.** No real names in the profile, no email, no location history.
5. **Check every frame for NASA logos** — including the basemap attribution line and any satellite imagery credit.
   Text attribution ("Data: NASA POWER, GRACE-FO, MODIS") is fine; the meatball is not.
6. **Record at 60 fps**, export 1080p H.264, audio −16 LUFS, captions burned in plus an `.srt` alongside.

## Edit checklist

- [ ] Runtime ≤ 29.5 s, verified in the exported file — not in the timeline.
- [ ] Every on-screen label readable at 720p on a laptop at arm's length.
- [ ] Captions match the voice-over word for word, including "can't tell yet".
- [ ] No text within 5 % of the frame edge (players crop).
- [ ] No NASA logo, no NASA seal, no "NASA" used as a visual brand.
- [ ] No music, or music we own or that is licensed for this use, credited in the description.
- [ ] If any AI-generated image ever enters the cut: visible watermark `AI-generated` + a line in the description.
      (Current plan: none. All shots are screen capture.)
- [ ] Uploaded public or unlisted-but-link-accessible, tested in a private window with no session.
- [ ] Description repeats the AI disclosure and the data credits.

---

## Appendix — if we ship the 7-slide deck instead

The rules allow either format, never both. If the video falls through, the same six beats map onto seven slides:

| Slide | Content | Beat from the script |
|---|---|---|
| 1 | Title: Earth Trend Detective, team name, challenge | — |
| 2 | The problem: satellites measure it, nobody explains it | 0–3 s |
| 3 | Lake Mead: storage falls, rainfall flat — the question | 3–8 s |
| 4 | How it works: sweep → significance → residual → explanation | 8–21 s |
| 5 | Explore mode screenshot: any place, one verdict | 8–14 s |
| 6 | The validator: why the AI cannot invent a number | 21–26 s |
| 7 | Limits, NASA data used, next step, links | 26–30 s |

Slide count includes the title slide. Seven is the maximum, not a target.
