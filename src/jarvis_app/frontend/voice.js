"use strict";
/* Browser-owned speech only. Transcripts use the existing authenticated chat route. */
function createJarvisVoice({env, mic, mute, stop, status, input, submit, isBusy}) {
  const Recognition = env.SpeechRecognition || env.webkitSpeechRecognition;
  const synth = env.speechSynthesis;
  const canSpeak = Boolean(synth && env.SpeechSynthesisUtterance);
  let recognition = null, listening = false, muted = false, utterance = null;
  const show = text => { status.textContent = text; };
  function stopSpeaking() {
    utterance = null;
    if (canSpeak) synth.cancel();
    stop.disabled = true;
  }
  function resetMic() {
    listening = false;
    mic.setAttribute("aria-pressed", "false");
    mic.setAttribute("aria-label", "Start microphone");
    mic.title = "Start microphone";
  }
  const errors = {
    "not-allowed": "Microphone permission denied. Allow microphone access in browser/site settings, then try again.",
    "service-not-allowed": "Speech recognition permission denied by the browser. Check browser/site settings.",
    "audio-capture": "No microphone available. Connect a microphone and check its permissions.",
    "no-speech": "No speech detected. Click the microphone and try again.",
    "network": "Browser speech recognition could not connect. Check your connection and try again.",
    "language-not-supported": "Speech recognition does not support this browser language."
  };
  if (!Recognition) {
    mic.disabled = true;
    show("Speech recognition is unsupported in this browser. You can still type messages.");
  } else if (env.isSecureContext === false) {
    mic.disabled = true;
    show("Microphone access requires HTTPS or localhost. Open http://127.0.0.1:8770 on this Mac.");
  }
  mic.addEventListener("click", () => {
    if (listening) { resetMic(); recognition.abort(); show("Microphone stopped."); return; }
    if (isBusy()) { show("Wait for Jarvis to finish before using the microphone."); return; }
    stopSpeaking();
    try {
      recognition = new Recognition();
      const session = recognition;
      recognition.lang = env.navigator.language || "en-US";
      recognition.continuous = false;
      recognition.interimResults = true;
      let submitted = false, failed = false, finalText = "";
      listening = true;
      mic.setAttribute("aria-pressed", "true");
      mic.setAttribute("aria-label", "Stop microphone");
      mic.title = "Stop microphone";
      show("Requesting microphone permission…");
      recognition.onstart = () => { if (recognition === session && listening) show("Listening… Speak your message."); };
      recognition.onresult = event => {
        if (recognition !== session || !listening || failed || submitted) return;
        const final = [], interim = [];
        for (let i = 0; i < event.results.length; i++) {
          (event.results[i].isFinal ? final : interim).push(event.results[i][0].transcript);
        }
        finalText = final.join(" ").trim();
        input.value = [...final, ...interim].join(" ").trim();
      };
      recognition.onerror = event => {
        if (recognition !== session) return;
        failed = true; resetMic();
        show(errors[event.error] || (event.error === "aborted" ? "Microphone stopped." : "Speech recognition failed: " + event.error));
      };
      recognition.onend = () => {
        if (recognition !== session) return;
        const shouldSend = listening && !failed && !submitted && finalText;
        resetMic();
        if (shouldSend) {
          if (finalText.length > input.maxLength) { show("Recognized message is too long. Shorten it before sending."); return; }
          if (isBusy()) { show("Jarvis is busy. Your transcript is in the input; send it when ready."); return; }
          submitted = true;
          input.value = finalText;
          show("Voice message sent.");
          submit(finalText);
        } else if (!failed && !submitted) show("Microphone stopped. No message sent.");
      };
      recognition.start();
    } catch (error) { resetMic(); show(errors[error.name === "NotAllowedError" ? "not-allowed" : ""] || "Could not start microphone: " + error.message); }
  });
  mute.disabled = !canSpeak;
  if (!canSpeak && Recognition) show("Spoken responses are unsupported in this browser.");
  mute.addEventListener("click", () => {
    muted = !muted;
    mute.textContent = muted ? "Unmute" : "Mute";
    mute.setAttribute("aria-pressed", String(muted));
    if (muted) stopSpeaking();
    show(muted ? "Spoken responses muted." : "Spoken responses enabled.");
  });
  stop.addEventListener("click", () => { stopSpeaking(); show("Speech stopped."); });
  env.addEventListener("pagehide", () => { stopSpeaking(); if (recognition) recognition.abort(); resetMic(); });
  return {
    stopSpeaking,
    speak(text) {
      if (!canSpeak || muted || !text || listening) return;
      stopSpeaking();
      const current = new env.SpeechSynthesisUtterance(text);
      utterance = current;
      current.lang = env.navigator.language || "en-US";
      const local = synth.getVoices().find(v => v.localService && v.lang === current.lang);
      if (local) current.voice = local;
      current.onend = () => { if (utterance === current) { utterance = null; stop.disabled = true; } };
      current.onerror = event => {
        if (utterance !== current) return;
        utterance = null; stop.disabled = true;
        show("Could not speak response: " + event.error);
      };
      stop.disabled = false;
      try { synth.speak(current); } catch (error) { stopSpeaking(); show("Could not speak response: " + error.message); }
    }
  };
}
