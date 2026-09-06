# Changelog

## [1.7.1](https://github.com/Schnee111/shorekeeper-cascade-agent/compare/shorekeeper-cascade-agent-v1.7.0...shorekeeper-cascade-agent-v1.7.1) (2026-09-06)


### Bug Fixes

* **deps:** sync uv.lock with v1.7.0 ([435482c](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/435482c8472c3210f125bd412d3f299041913482))

## [1.7.0](https://github.com/Schnee111/shorekeeper-cascade-agent/compare/shorekeeper-cascade-agent-v1.6.0...shorekeeper-cascade-agent-v1.7.0) (2026-09-06)


### Features

* allow 2-3 prosody cues per reply on emotional shifts ([3332c70](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/3332c70864096bb7a11ad830d28149829c54ea17))
* allow free-form Fish Audio prosody cues in replies ([c5d658b](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/c5d658bb5905e870b198bed865aa32e2d351d83d))
* anti-silence filler engine v2 — voice overlaps tool waits ([5e28b63](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/5e28b6344155c0932e0289d0e4d7d9657e9191c5))
* change greeting to English, brand as Shorekeeper ([81399a9](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/81399a991570e64d456109080168affe46eb72ca))
* **docker:** add production multi-stage dockerfile and resource-limited compose ([fd85222](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/fd8522256419408926e87d3a48e999fee4952835))
* **filler:** add 2.0s early ack filler to mask LLM API queue latency ([be16beb](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/be16beb8a97e28eae265490c0598aa155748ecab))
* **filler:** Smart Filler Engine v6 with decimal-aware sentence splitting ([8084320](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/80843205b0fc669595d531f4e7bbdfb3b3a9192e))
* **filler:** tune early ack threshold to 2.8s and introduce natural disfluency pools ([500888e](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/500888eb1d4bb5cf49938f1034a12fa0d9e2bbd2))
* live voice switcher (token attributes → participant → TTS) ([42a41e9](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/42a41e92fb846ee1f941d0b01414560c4084a969))
* LLM adds Fish Audio prosody cues to every turn reply ([c4f3642](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/c4f3642b6fa8679a6f4035b1ac949ea5ab430859))
* **manifest:** rename project to shorekeeper-cascade-agent v1.0.0 ([14d166d](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/14d166de3bec45da3ef9dbc7f9befca3dc871c3d))
* publish tool-activity events to room for UI chip ([2c53509](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/2c53509e86a78062e7fcd87a3918024e0d5d05c0))
* rotate personalized greetings to Schnee with Fish prosody cues ([410920a](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/410920a05d188ae855f593bf2ee3c840ce6106a8))
* **stt:** upgrade speech-to-text to Groq Whisper large-v3-turbo with Deepgram fallback ([64c452e](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/64c452ec2d08f394ba65a13dd36ea06a90235731))
* **token-server:** add model_override query parameter support for LiveKit participant metadata ([17379fb](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/17379fb0576a86790ff53fc073e02217d573b84d))
* **tts:** add automatic number normalization to spoken words for Fish Audio TTS ([1f65c74](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/1f65c742b15826c915bfc067cdd54428f9077fd9))
* voice instructions English-first, Indonesian only on explicit request ([cc0f17b](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/cc0f17baa4f4946ef1f47a238cf555f8c06310e1))
* voice layer — instructions prepend, sentence cleaner, filler engine, greeting ([2f09338](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/2f093380f10b106b455a59d73ba1a2dd14ca8b28))
* voice registry entries carry short desc labels for the UI ([ba8693f](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/ba8693f68285242785a478109426b52178733183))
* **voice:** enforce 1-3 tool limit in voice mode and delegate heavy loops ([5d13efa](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/5d13efa4fa95fd7ffb30c9dbc4502d66d9242ded))
* **voice:** register 7 Indonesian Fish Audio voice model IDs in token server ([6b1dd44](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/6b1dd44b3fd5e8c710c416aa8d7412f2dbf5d16e))
* **voice:** tune endpointing 0.5s, session pre-warm, and diverse dynamic fillers ([a39595b](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/a39595b52df969ec45801efcad7ad4e1f08b301f))
* **voice:** update token server with EN & JP voice model mapping ([04a8fd2](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/04a8fd225d0d332d0d82433987ee8569a69adb91))


### Bug Fixes

* add missing WORKDIR /app in production stage ([#57](https://github.com/Schnee111/shorekeeper-cascade-agent/issues/57)) ([95bedcd](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/95bedcd58182465f29127b9fbd9d8c626fe94aab))
* **agent:** make shutdown callback async and auto-kill child processes to prevent zombies ([76b163a](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/76b163a28972fdf0414dd8cfcbd864331bc84552))
* **agent:** stop forkserver orphans on voice/model switch (RAM leak) ([ba40ecd](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/ba40ecde6442fa425e88ce5877065ecdeabd30fb))
* **agent:** tune VAD endpointing and enable VAD interruption with false-interruption resumption ([dfd3fce](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/dfd3fce9d691b2e38e6106637fab95300e0a19be))
* always terminate TTS chunks with a space ([be869a5](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/be869a56b726e4d17bcd8435ebaa376fe06b8a27))
* **bridge:** resolve multi-tool active count desync and suppression deadlock (fixes [#1](https://github.com/Schnee111/shorekeeper-cascade-agent/issues/1)) ([2867ce9](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/2867ce968871b5a77e46ad6dea217a0ac4f66e1e))
* cover tool CHAINS — silence-keyed acks + post-tool safety net ([cb2d4f4](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/cb2d4f48bb848d2c6225d48310fc80017a4f84fd))
* dead turns, stuck-thinking, and fragmented voice input ([995fca7](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/995fca740d5f648181459566128781e87516c2af))
* **deps:** sync uv.lock with shorekeeper-cascade-agent v1.6.0 ([9e26aeb](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/9e26aeb85c92c7df7d29bb4fb9c7a270bb37542c))
* disable second filler path (tool.generating → FILLER_TOOL) ([c318497](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/c3184979067b09b0bbaa19299897324e78175cc0))
* **docker:** use python@3.14 and d/l models to shared dir ([#78](https://github.com/Schnee111/shorekeeper-cascade-agent/issues/78)) ([5d1074e](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/5d1074eee8bd146c6bc9093f04bd49c25d74ff20))
* dynamic endpointing floor 1.2s + restore token_server contracts ([d3cc142](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/d3cc1426219036f2281605e0a6d8febb470aa9c7))
* **hermes_llm:** instant pre-tool flush for LLM opening sentence ([64c1127](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/64c1127468a0d00c8b088f9300c5f90ecfd002d3))
* **hermes_llm:** scaffold filter actually gates TTS + timing log ([f437047](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/f4370474ea8d8c465085d4db4bf4866ddb524580))
* **hermes-llm:** instant sentence buffer flush before tool execution and orphan bracket sanitization ([1f5524b](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/1f5524b5918ed27e3db45f803dd9155969178772))
* migrate default AIC model to VF_S ([#74](https://github.com/Schnee111/shorekeeper-cascade-agent/issues/74)) ([23271e0](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/23271e05955b57b6359df69d545890cc742de33e))
* never let em/en dashes reach TTS — Fish reads them without pause ([5ad324d](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/5ad324d4e145b9b4920965ee6c1e4e43bb5758eb))
* probe resolves .env.local from repo root regardless of cwd ([3f0bf33](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/3f0bf333f3e73249a5d305787a97708311c8a776))
* prompt shutdown on user departure — kills 30-45s process linger ([7536a8e](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/7536a8ec031eb3b84e0669903d546f5e978c4e3f))
* reduce premature turn commits fragmenting user utterances ([28ebbdf](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/28ebbdf01254f3d0738c1bbb3d6f7220b0969929))
* **root-cause:** TTS tokenizer holds last sentence — flush per filler ([a8939a2](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/a8939a26c19a7b77d640c557f1046335154c0b01))
* **security:** bind token server explicitly to 127.0.0.1 ([3bcdcd3](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/3bcdcd31e6cd78fd7e930bdc41c4a78aa9d2d3b5))
* serialize turn lifecycle to prevent WS recv ConcurrencyError ([52b6e70](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/52b6e70e1ac2e4998708c3d1749199beab86d405))
* strip steering scaffolds + bracket cues server-side; tune endpointing v2 ([8c4feb7](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/8c4feb748d4f046dc992869ab63447056bad4417))
* **tts,stt:** lock 48kHz sample rate on Fish TTS and enable prompt-biased Whisper large-v3 (fixes [#4](https://github.com/Schnee111/shorekeeper-cascade-agent/issues/4)) ([8f806dd](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/8f806ddbdf876e46098dc258579831953bd4d6b5))
* **tts:** decouple UI raw text streaming from TTS sentence normalization ([713fd6a](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/713fd6a659389b6d35188cd619ddd63dae429c2d))


### Documentation

* architecture & status snapshot (turn detection cloud v1, quotas, watchpoints) ([98a2dbc](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/98a2dbc2e2de4aa3667ab4109ddaa646970922fd))
* bun prototype fully decommissioned — production is 100% LiveKit ([7018e76](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/7018e7664089ecfd9545f2017c7274320b349bd4))
* elevate README to elite open-source standard with architecture diagram and feature matrix ([06d7df0](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/06d7df0d0efb01dc6a395687bdf0f0e8f8825cda))
* modernize README and update MIT license with dual attribution ([a331e03](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/a331e0370d3525342ac9d792a39538e402e8b37b))
* use long-form flags in lk app env example ([#87](https://github.com/Schnee111/shorekeeper-cascade-agent/issues/87)) ([d48dfda](https://github.com/Schnee111/shorekeeper-cascade-agent/commit/d48dfda85d9e3537f35dd642c0b01be6a24bfa53))
