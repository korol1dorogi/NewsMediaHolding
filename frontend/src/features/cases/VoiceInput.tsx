import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

// A7: browser speech recognition. No audio reaches our server; the browser may send it to
// its vendor (Chrome uses Google), so the user is told before starting.
type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};
type RecognitionClass = new () => Recognition;

function recognitionClass(): RecognitionClass | null {
  const scope = globalThis as unknown as {
    SpeechRecognition?: RecognitionClass;
    webkitSpeechRecognition?: RecognitionClass;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export function VoiceInput({ onText }: { onText: (text: string) => void }) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const Klass = recognitionClass();

  useEffect(() => () => recognition.current?.stop(), []);

  if (!Klass) return null;

  function start() {
    if (!Klass) return;
    const instance = new Klass();
    instance.lang = "ru-RU";
    instance.interimResults = false;
    instance.continuous = false;
    instance.onresult = (event) => {
      const text = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (text) onText(text);
    };
    instance.onerror = () => setError(true);
    instance.onend = () => setListening(false);
    recognition.current = instance;
    setError(false);
    setListening(true);
    instance.start();
  }

  return (
    <div className="space-y-1">
      <Button
        variant="outline"
        onClick={() => (listening ? recognition.current?.stop() : start())}
        aria-pressed={listening}
      >
        {listening ? "Остановить запись" : "Надиктовать"}
      </Button>
      <p className="text-xs text-muted">
        Речь распознаёт ваш браузер; Chrome отправляет звук в Google. Проверьте текст перед
        отправкой.
      </p>
      {error && (
        <p role="alert" className="text-xs text-red-700">
          Не удалось распознать речь. Разрешите доступ к микрофону или введите текст.
        </p>
      )}
    </div>
  );
}

export function appendText(current: string, addition: string) {
  return current.trim() ? `${current.trimEnd()} ${addition}` : addition;
}
