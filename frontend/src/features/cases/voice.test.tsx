import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderAt } from "./testing";
import { appendText } from "./VoiceInput";

afterEach(() => vi.unstubAllGlobals());

class FakeRecognition {
  static last: FakeRecognition | null = null;
  lang = "";
  interimResults = true;
  continuous = true;
  onresult: ((event: { results: { transcript: string }[][] }) => void) | null = null;
  onerror: (() => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn(() => {
    FakeRecognition.last = this;
  });
  stop = vi.fn(() => this.onend?.());
}

describe("A7 voice input", () => {
  it("is hidden when the browser cannot recognise speech", async () => {
    mockApi({});
    renderAt("/user/new");
    expect(await screen.findByLabelText(/Что произошло/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Надиктовать" })).not.toBeInTheDocument();
  });

  it("appends recognised Russian speech to the text and warns about the vendor", async () => {
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
    mockApi({});
    renderAt("/user/new");
    const text = await screen.findByLabelText(/Что произошло/);
    fireEvent.change(text, { target: { value: "Курс не вернули." } });
    expect(screen.getByText(/Chrome отправляет звук в Google/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Надиктовать" }));
    const recognition = FakeRecognition.last;
    expect(recognition?.lang).toBe("ru-RU");
    expect(screen.getByRole("button", { name: "Остановить запись" })).toBeInTheDocument();
    act(() => {
      recognition?.onresult?.({ results: [[{ transcript: "Оплатила 1 октября" }]] });
      recognition?.onend?.();
    });
    expect(text).toHaveValue("Курс не вернули. Оплатила 1 октября");
    expect(await screen.findByRole("button", { name: "Надиктовать" })).toBeInTheDocument();
  });

  it("joins text with a single space", () => {
    expect(appendText("", "привет")).toBe("привет");
    expect(appendText("текст  ", "ещё")).toBe("текст ещё");
  });
});
