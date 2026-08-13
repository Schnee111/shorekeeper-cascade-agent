# JARVIS LiveKit → UI Integration Plan (FINAL)

> Self-contained brief untuk fresh session implementasi. Dibuat 2026-08-13.
> Status pipeline saat ini: **voice loop sudah jalan end-to-end** (Deepgram id → Hermes → Fish TTS free),
> terverifikasi lewat test page `/jarvis-livekit/index.html`. Tugas ini = integrasi ke UI Svelte produksi.

## 1. Arsitektur

```
Browser (Svelte UI, deploy: /var/www/jarvis/, route nginx /jarvis/)
   │  livekit-client v2.21.0 (sudah terinstall di client/)
   │  WebRTC: mic capture + playback otomatis oleh SDK
   ▼
LiveKit Cloud SFU  wss://shore-eoiag4jd.livekit.cloud
   │  auto-dispatch agent via JWT room_config (sudah jalan)
   ▼
Agent "jarvis"  (systemd: jarvis-agent.service, cwd /home/ubuntu/projects/jarvis-livekit)
   deepgram.STT(nova-3, language="id")
   → HermesLLM (WS bridge ke Hermes Gateway)
   → inference.TTS("fishaudio/s2.1-pro-free", voice="3095f8e1d1fa4b82acaa8aca720a7f83")
   ▼
Hermes Gateway  ws://127.0.0.1:9119/api/ws  (1 session persistent per room)
```

Endpoint token: relative `/jarvis-livekit/token?room=<room>&identity=<identity>`
(proxy nginx → token_server.py port 8082, JWT sudah include RoomAgentDispatch jarvis). Sudah verified 200.

## 2. Keputusan Terkunci (dari user)

| Item | Keputusan |
|---|---|
| Soul | Hermes coding assistant default + voice formatting layer (prepend di bridge) |
| Voice selector UI | KEEP (untuk sekarang kosmetik/placeholder, hanya Vestia Zeta) |
| Wake word + tap | DUA-DUANYA ada; tap = jalur utama sekarang, wake word UX disetel kemudian |
| Room | Per-session: `jarvis-{random8}`, identity `schnee` |
| Handling markdown | **V1 clean-at-source** (dual-channel data message = later) |
| Greeting | Auto saat user join: "Halo! Aku JARVIS, ada yang bisa dibantu?" |
| Anti-silence tool call | Filler engine di bridge |
| Anti-halusinasi STT | Guard best-effort di agent |

## 3. ⚠️ FAKTA KRUSIAL (verified di kode, jangan salah lagi)

1. **`instructions=` di agent.py TIDAK pernah sampai ke Hermes.** `hermes_llm.py` hanya
   mengambil pesan user terakhir dari `chat_ctx.to_provider_format()` (return-nya TUPLE
   `(messages, tools)` — bug lama sudah difix). Voice instructions HARUS di-prepend
   di `hermes_llm.py` setiap submit.
2. `expressive=True` di agent.py saat ini dead config (Hermes tidak melihat prompt
   LiveKit) → set `False` biar bersih.
3. Event tool call Hermes Gateway (verified di tui_gateway/server.py:5122,5379):
   - `tool.generating` → payload `{"name": ...}` (tool mulai)
   - `tool.complete`  → tool selesai
   Plus `thinking.delta`, `message.delta` (field `text`), `message.complete`.
4. `session.say(text)` tersedia di AgentSession untuk greeting.
5. livekit-client: `RoomEvent.TranscriptionReceived` → handler
   `(transcription: TranscriptionSegment[], participant?, publication?)`;
   `TranscriptionSegment = {id, text, language, startTime, endTime, final,
   firstReceivedTime, lastReceivedTime}`.
6. Autoplay: panggil `room.startAudio()` di dalam gesture tap orb.
7. Server Bun lama (port 3002, /jarvis/ws) TIDAK dipakai lagi oleh UI baru —
   biarkan jalan, jangan dihapus/di-kill (di luar scope).

## 4. Handling: 4 Lapis

### Lapis 1 — Voice instructions (hermes_llm.py, prepend tiap submit)
```
[VOICE MODE] Kamu sedang voice call dengan user.
- Jawab PLAIN TEXT: tanpa markdown, tanpa code block, tanpa list/tabel, tanpa emoji, tanpa URL mentah.
- 1-3 kalimat, conversational, satu pertanyaan tiap kali.
- Eja angka, telepon, tanggal bila penting.
- Jawab dalam bahasa yang dipakai user (Indonesia/Inggris).
- Kalau diminta kode/teknis: jelaskan singkat secara verbal, jangan tampilkan kode/syntax.
```
Stateless, di-prepended ke setiap prompt.submit.

### Lapis 2 — Sentence cleaner (hermes_llm.py, jaminan TTS)
Buffer delta dari `message.delta` → potong di batas kalimat (`. ! ? \n` + min length)
→ clean tiap kalimat → yield ChatChunk. Latency +0 (TTS memang nunggu kalimat lengkap).

Clean per kalimat:
- strip sisa markdown: `` ` `` `*` `_` `#` `|` `-` bullet prefix `[ ]( )`
- code block/fence yang lolos → ganti "[potongan kode]"
- URL → "link", email → "alamat email"
- emoji semua range Unicode + zero-width/BOM + control chars (kecuali \n)
- normalize `!!!`→`!`, literal `\n\n`, mojibake umum (`â€”`→`-`)
- strip whitespace berlebih

### Lapis 3 — Filler engine (hermes_llm.py, async timer)
- Start timer 2 detik saat submit.
- Kalau ada event `thinking.delta`/`message.delta` sebelum 2 detik → cancel (normal).
- >2 detik tanpa activity → emit ChatChunk filler: "Bentar ya, aku cek dulu..."
- Terima `tool.generating` → emit filler kontekstual ("Aku lagi coba cek, sebentar...")
  jika belum ada filler & belum ada text.
- Timer lanjutan 10 detik → filler kedua ("Masih aku proses, sebentar lagi...") max 2 filler.
- Implementasi: satu task pembaca WS events + `asyncio.wait`/timeout; filler = yield
  ChatChunk langsung ke `_event_ch` sebelum text asli.

### Lapis 4 — Client (voice-text.ts + App.svelte)
`cleanVoiceText()` (subset lapis 2, buat subtitle + safety net display):
markdown strip, emoji strip, URL→"link", kontrol chars, normalisasi.
- Subtitle: SELALU cleanVoiceText
- Conversation panel: teks bersih (V1 = tidak ada markdown untuk dirender;
  pertahankan line breaks). Tidak perlu marked/dompurify di V1.
- CSS `overflow-wrap: break-word` untuk URL panjang.
- Segment accumulation: Map key = `turnIndex + segmentId`; update hanya jika teks
  berubah (anti-flicker); final → push ke history.
- Bahasa badge subtitle dari `segment.language`.

### Case STT (agent.py, best-effort)
Deepgram hallucination guard: track last-VAD-speech timestamp; bila
`user_input_transcribed` final datang tanpa speech VAD dalam ~3 detik terakhir
dan/atau match pola halusinasi umum → ignore. Jika hook ternyata rumit,
andalkan TurnDetector (akustik+semantik) dan catat sebagai known limitation.

## 5. File Changes

### Baru
| File | Isi |
|---|---|
| `client/src/lib/livekit-voice.ts` (~200 baris) | connect(roomName) → fetch token → `new Room()` → `room.connect(LIVEKIT_URL, token)` → `room.startAudio()` → `setMicrophoneEnabled(true)`. Events: TranscriptionReceived (→ callback segments), TrackSubscribed (attach audio element agent), ActiveSpeakersChanged (→ speaking state), Disconnected/Reconnecting (→ callback). Export start/stop + subscribe pattern. |
| `client/src/lib/voice-text.ts` (~60 baris) | cleanVoiceText() |

### Rewrite
| File | Perubahan |
|---|---|
| `client/src/App.svelte` | Ganti seluruh logic WebSocket → livekit-voice. PERTAHANKAN: Orb + semua animasi/CSS, state (off/standby/active, listening/processing/speaking), conversation panel, system logs, voice selector (kosmetik), wake word scaffolding. TAMBAH: segment→subtitle/history, greeting state, autoplay resume via room.startAudio() di tap. |

### Hapus dari pemakaian
- `client/src/lib/audio-capture.ts`, `audio-playback.ts` → hapus file (digantikan SDK).
- `client/src/lib/wakeword.ts` → TETAP dipakai (standby).

### Modifikasi agent
| File | Perubahan |
|---|---|
| `jarvis-livekit/src/hermes_llm.py` | Lapis 1+2+3 di atas. |
| `jarvis-livekit/src/agent.py` | `expressive=False`; greeting di `my_agent()`: sebelum/bersamaan connect, `participant = await ctx.wait_for_participant(identity="schnee")` lalu `await session.say("Halo! Aku JARVIS, ada yang bisa dibantu?")` (API verified ada). |

### Dependencies
- `livekit-client@2.21.0` sudah terinstall. Tidak ada dependency baru lain (V1).

## 6. State Machine UI

```
OFF ──tap orb──► CONNECTING ──► ACTIVE (listening ⇄ processing ⇄ speaking)
OFF ──(arm wakeword)──► STANBY ──"Hey Jarvis"──► CONNECTING ──► ACTIVE
ACTIVE ──tap orb / disconnect──► OFF (room.disconnect, stop mic)
```
- Tap orb = user gesture → penuhi autoplay policy (panggil room.startAudio()).
- Wake word: stop openwakeword TOTAL dulu (bebasin mic) baru connect LiveKit.
- Status orb: listening = mic on & user belum final; processing = final transcript
  diterima, belum ada segment agent; speaking = segment agent masuk ATAU agent di
  ActiveSpeakersChanged.

## 7. Deploy & Verifikasi Internal (WAJIB sebelum serah terima ke user)

1. `vite build` lolos tanpa error.
2. Unit test cleanVoiceText(): markdown, tabel, emoji, URL, code block, zero-width,
   mojibake, repeated punctuation.
3. Test bridge (script `HermesLLM.chat()` langsung):
   - prompt pancingan: "buatkan tabel 3 kolom", "tulis kode python hello world"
     → output stream harus bersih dari markdown/simbol.
   - prompt berat (memicu tool call Hermes, mis. "cek isi folder /tmp")
     → filler "Bentar ya..." muncul sebelum jawaban.
4. Restart `sudo systemctl restart jarvis-agent` → journalctl: registered, tanpa traceback.
5. Deploy client ke /var/www/jarvis/ → curl https://tethys.web.id/jarvis/ = 200.
6. journalctl saat connect: participant join, input stream attached, greeting
   ke-stream, user_speech terdeteksi, turn complete.
7. Baru minta user test di mobile.

## 8. Risiko / Catatan

- Fish Audio s2.1-pro **free** promo berakhir ~31 Agustus 2026 (cek pricing LiveKit).
- Room baru = Hermes session baru → konteks percakapan tidak persist antar kunjungan
  (acceptable; future: session naming persisten).
- Voice selector belum fungsional (1 voice). Future: LiveKit attributes → agent swap voice.
- Subtitle agent realtime bergantung TranscriptionReceived dari AgentSession —
  verifikasi di step 7.6; fallback: history dari data message.
- Token server & agent systemd harus jalan: cek `systemctl status jarvis-agent` dan
  proses token_server.py (port 8082).
- Credential: JANGAN commit/print API key & token; pakai [REDACTED] di catatan.

## 9. Urutan Eksekusi yang Disarankan

1. voice-text.ts + unit test (cepat, independen)
2. hermes_llm.py: instructions prepend → sentence cleaner → filler (test per lapis via script)
3. agent.py: expressive=False + greeting → restart service + verify journalctl
4. livekit-voice.ts
5. App.svelte rewrite → build → deploy
6. Verifikasi internal penuh (section 7) → serah terima
