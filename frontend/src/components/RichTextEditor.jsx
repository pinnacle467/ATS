import { useEffect, useRef } from 'react';
import { Bold, Italic, List, ListOrdered, Underline, Heading } from 'lucide-react';

/**
 * Lightweight dependency-free rich-text editor (contentEditable + execCommand).
 * Emits HTML via onChange. Good enough for composing offer letters — bold,
 * italic, underline, headings and lists.
 */
export default function RichTextEditor({ value, onChange, placeholder, testId }) {
  const ref = useRef(null);

  // Sync external value into the DOM only when it differs and we're not actively
  // typing (prevents the caret from jumping on every keystroke).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (document.activeElement !== el && (value || '') !== el.innerHTML) {
      el.innerHTML = value || '';
    }
  }, [value]);

  const exec = (command, arg = null) => {
    ref.current?.focus();
    document.execCommand(command, false, arg);
    onChange?.(ref.current?.innerHTML || '');
  };

  const btn =
    'inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors';

  return (
    <div className="rounded-md border border-input bg-background" data-testid={testId}>
      <div className="flex items-center gap-0.5 border-b border-border px-1.5 py-1">
        <button type="button" className={btn} title="Bold" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('bold')} data-testid="rte-bold">
          <Bold className="h-4 w-4" />
        </button>
        <button type="button" className={btn} title="Italic" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('italic')} data-testid="rte-italic">
          <Italic className="h-4 w-4" />
        </button>
        <button type="button" className={btn} title="Underline" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('underline')} data-testid="rte-underline">
          <Underline className="h-4 w-4" />
        </button>
        <span className="mx-1 h-5 w-px bg-border" />
        <button type="button" className={btn} title="Heading" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('formatBlock', 'H3')} data-testid="rte-heading">
          <Heading className="h-4 w-4" />
        </button>
        <button type="button" className={btn} title="Bullet list" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('insertUnorderedList')} data-testid="rte-ul">
          <List className="h-4 w-4" />
        </button>
        <button type="button" className={btn} title="Numbered list" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('insertOrderedList')} data-testid="rte-ol">
          <ListOrdered className="h-4 w-4" />
        </button>
      </div>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={(e) => onChange?.(e.currentTarget.innerHTML)}
        data-placeholder={placeholder || 'Write the offer letter…'}
        data-testid="rte-content"
        className="rte-content min-h-[220px] max-h-[42vh] overflow-y-auto px-3 py-2 text-sm leading-relaxed focus:outline-none"
      />
    </div>
  );
}
