import type { HTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`rounded border p-2 ${props.className ?? ""}`} />;
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`rounded border p-2 ${props.className ?? ""}`} />;
}
export function Card(props: HTMLAttributes<HTMLElement>) {
  return <section {...props} className={`rounded border p-4 ${props.className ?? ""}`} />;
}
export function Badge(props: HTMLAttributes<HTMLSpanElement>) {
  return <span {...props} className={`rounded border px-2 py-1 ${props.className ?? ""}`} />;
}
export function Dialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <dialog open aria-label={title} onCancel={onClose}>
      <h2>{title}</h2>
      {children}
      <button type="button" onClick={onClose}>
        Закрыть
      </button>
    </dialog>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div role="status" aria-live="polite">
      {children}
    </div>
  );
}
