# Discord Portable TTS Attachment

A small, local desktop app that converts typed text to speech and routes it through VB‑CABLE so any application (Discord web/desktop, Zoom, Teams, etc.) can capture it as a microphone.

Key points

- No API key required: uses local system voices and the edge-tts package — nothing to register or paste into a config.
- High-quality neural voices: "Neural (Edge)" provides natural-sounding speech; `System (Windows)` is available as an offline fallback.
- Works in all apps: audio is sent to the VB‑Audio virtual cable, which user apps can select as an input/microphone.

Quick start (Windows)

1. Run the bundled EXE in dist (e.g., `dist\\discord_tts.exe`) or run `python discord_tts_attachment.py`.
2. In the app:
   - Select Engine: choose **Neural (Edge)** for best voice quality (requires internet) or **System (Windows)** to stay offline.
   - Ensure the Virtual output shows `CABLE Input (VB-Audio Virtual Cable)`.
   - (Optional) Set Secondary output to your speakers to monitor locally.
   - Type text and press **Speak** (or Ctrl+Enter).
3. In the target application (Discord/Zoom/etc.), set the Input/Recording device to the VB‑Audio cable endpoint (often shown as `CABLE Output`/`CABLE Input` depending on the app).

Privacy & offline behavior

- No API keys or cloud accounts are required to use the app. The neural voices use the edge-tts package and need internet access but do not require user API credentials.
- If you need fully offline TTS, switch to the `System (Windows)` engine — quality differs but it requires no network access.

Troubleshooting

- If the virtual cable doesn't appear, install or enable VB‑Audio Virtual Cable and restart the app.
- If the target app doesn't detect audio, confirm that the target app's Input Device matches the virtual cable device and disable aggressive voice processing (echo cancellation, noise suppression, AGC) in that app.
- For best compatibility with browsers and Discord web, the app sends 48 kHz mono audio to the virtual cable.

Contact

Open an issue if anything fails to work as expected; include the app status message and a short description of your audio device setup.
