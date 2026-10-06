import type { Citation, ComposerMode } from '../domain/thread.js';
import type { Locale } from '../i18n/i18n.js';

/**
 * There is no backend (see the project brief). This simulates one: it turns
 * a prompt into a plausible, mode-flavoured answer and streams it out in
 * small bursts, exactly like a real token stream would — including
 * `stop()` keeping whatever was emitted so far, and being resumable so a
 * "Continue" action (ux-foundations.md §4.3) can pick the same stream back
 * up rather than starting over.
 */

export interface MockStreamOptions {
  readonly minChunkDelayMs: number;
  readonly maxChunkDelayMs: number;
}

const DEFAULT_OPTIONS: MockStreamOptions = { minChunkDelayMs: 12, maxChunkDelayMs: 48 };

/** Splits on whitespace boundaries but keeps the whitespace, so re-joining chunks reproduces
 * the source text exactly — the same shape a real token stream's pieces would need to have. */
function tokenize(text: string): string[] {
  return text.match(/\S+\s*/g) ?? [text];
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

export class MockAssistantStream {
  readonly #chunks: string[];
  #position = 0;
  #timer: ReturnType<typeof setTimeout> | null = null;
  #stopped = false;

  constructor(
    readonly fullText: string,
    private readonly options: MockStreamOptions = DEFAULT_OPTIONS,
  ) {
    this.#chunks = tokenize(fullText);
  }

  get isComplete(): boolean {
    return this.#position >= this.#chunks.length;
  }

  get emittedText(): string {
    return this.#chunks.slice(0, this.#position).join('');
  }

  /** Begins (or resumes, after `stop()`) emitting chunks. `onChunk` receives the new piece and
   * the full text emitted so far; `onDone` fires once when the stream is exhausted. */
  start(onChunk: (chunk: string, textSoFar: string) => void, onDone: () => void): void {
    this.#stopped = false;
    const step = (): void => {
      if (this.#stopped) return;
      if (this.#position >= this.#chunks.length) {
        onDone();
        return;
      }
      const chunk = this.#chunks[this.#position];
      this.#position += 1;
      if (chunk !== undefined) onChunk(chunk, this.emittedText);
      this.#timer = setTimeout(
        step,
        randomBetween(this.options.minChunkDelayMs, this.options.maxChunkDelayMs),
      );
    };
    step();
  }

  /** ux-foundations.md §4.3 — "Stopped by user: partial reply is kept ... with Continue." Stops
   * emitting without discarding position, so a later `start()` resumes rather than restarts. */
  stop(): void {
    this.#stopped = true;
    if (this.#timer !== null) clearTimeout(this.#timer);
    this.#timer = null;
  }
}

export interface MockReply {
  readonly stream: MockAssistantStream;
  readonly citations: Citation[];
}

function topicFrom(prompt: string): string {
  const trimmed = prompt.trim().replace(/\s+/g, ' ');
  if (trimmed.length === 0) return 'this';
  return trimmed.length > 72 ? `${trimmed.slice(0, 72)}…` : trimmed;
}

const TEMPLATES: Record<Locale, Record<ComposerMode, (topic: string) => string>> = {
  en: {
    learn: (topic) => `## Starting from the fundamentals

"${topic}" breaks down into a few core ideas that are worth separating before going further, because they usually get tangled together in a first pass.

**The first idea** is the one everything else depends on: a clear definition of the terms involved, stated plainly enough that you could explain it to someone hearing it for the first time.

**The second idea** builds on that definition and is where most of the useful intuition lives — the "why it works this way" rather than just the "what it is."

**The third idea** is the common misconception: it is tempting to assume the obvious mechanism is the whole story, but the interesting part is usually the exception that the simple version glosses over.

**In short:** start from the definition, build the intuition on top of it, and hold the obvious mechanism loosely until you have checked it against the exception. That order tends to make the rest stick.`,
    research: (topic) => `## What the sources agree on

Looking across the material on "${topic}", there is a consistent baseline: the core mechanism is well established and shows up the same way across independent write-ups. [1]

That baseline holds up under most conditions, though it is usually presented with fewer caveats than the primary sources actually include. [2]

## Where they diverge

The disagreement is less about the mechanism itself and more about how much it matters in practice — one line of sources treats it as a first-order effect, the other treats it as a secondary correction on top of something else. [3]

### Summary

- The core claim is well supported and replicated.
- The practical significance is genuinely contested, not just a matter of emphasis.
- Worth treating the strongest version of the claim with a bit of caution until you have read the primary source yourself.`,
    explore: (
      topic,
    ) => `Here are a few directions worth pulling on for "${topic}" — none of these are the "right" next step, just the ones that tend to open up the most:

- **Zoom out first** — what larger system is this a part of, and does it behave differently at that scale?
- **Find the edge case** — the situation where the usual explanation seems to almost, but not quite, apply.
- **Compare it to its closest neighbour** — the adjacent idea people most often confuse this with, and exactly where they stop being the same thing.
- **Trace it backward** — what had to already be true for this to have come up as a question at all?

Any of these worth going deeper on, or is there a fifth direction closer to what you actually need?`,
  },
  es: {
    learn: (topic) => `## Empezando por lo fundamental

"${topic}" se puede separar en algunas ideas centrales que conviene distinguir antes de avanzar, porque normalmente se mezclan en una primera lectura.

**La primera idea** es de la que dependen todas las demás: una definición clara de los términos, planteada con la sencillez suficiente como para explicársela a alguien que la escucha por primera vez.

**La segunda idea** se construye sobre esa definición y es donde vive la mayor parte de la intuición útil: el "por qué funciona así" y no solo el "qué es".

**La tercera idea** es el malentendido más común: es tentador asumir que el mecanismo obvio es toda la historia, pero lo interesante suele estar en la excepción que la versión simple pasa por alto.

**En resumen:** parte de la definición, construye la intuición sobre ella y sostén el mecanismo obvio con cautela hasta contrastarlo con la excepción. Ese orden suele hacer que quede claro.`,
    research: (topic) => `## En qué coinciden las fuentes

Al revisar el material sobre "${topic}", hay una base consistente: el mecanismo central está bien establecido y aparece igual en fuentes independientes. [1]

Esa base se sostiene en la mayoría de las condiciones, aunque suele presentarse con menos matices de los que incluyen las fuentes primarias. [2]

## En qué difieren

El desacuerdo no es tanto sobre el mecanismo en sí, sino sobre cuánto importa en la práctica: una línea de fuentes lo trata como un efecto de primer orden, la otra como una corrección secundaria sobre otra cosa. [3]

### Resumen

- La afirmación central está bien respaldada y se repite entre fuentes.
- Su importancia práctica sí está genuinamente en disputa, no es solo una cuestión de énfasis.
- Conviene tomar la versión más fuerte de la afirmación con cautela hasta leer la fuente primaria.`,
    explore: (
      topic,
    ) => `Aquí hay algunas direcciones que vale la pena explorar sobre "${topic}" — ninguna es "la" siguiente movida, solo las que suelen abrir más camino:

- **Alejar la mirada primero** — ¿de qué sistema más grande forma parte esto, y se comporta distinto a esa escala?
- **Buscar el caso límite** — la situación en la que la explicación habitual casi, pero no del todo, aplica.
- **Compararlo con su vecino más cercano** — la idea adyacente con la que más se confunde, y el punto exacto donde dejan de ser lo mismo.
- **Rastrearlo hacia atrás** — ¿qué tenía que ser cierto ya para que esto surgiera como pregunta?

¿Alguna de estas vale la pena profundizar, o hay una quinta dirección más cercana a lo que necesitas?`,
  },
};

const SOURCE_TITLES: Record<Locale, string[]> = {
  en: [
    'A field guide to the core mechanism',
    'Independent replication and its limits',
    'Where practitioners disagree in practice',
  ],
  es: [
    'Una guía de campo sobre el mecanismo central',
    'Réplicas independientes y sus límites',
    'Dónde discrepa la práctica',
  ],
};

/** Builds one mock reply: a mode-flavoured, locale-flavoured canned answer (with citations for
 * Research mode) wrapped in a resumable, stoppable simulated stream. There is no real model
 * behind this — see the file header — so the "content" is intentionally generic rather than
 * responsive to the prompt beyond echoing its topic back. */
export function createMockReply(prompt: string, mode: ComposerMode, locale: Locale): MockReply {
  const topic = topicFrom(prompt);
  const text = TEMPLATES[locale][mode](topic);
  const citations: Citation[] =
    mode === 'research'
      ? SOURCE_TITLES[locale].map((title, i) => ({
          index: i + 1,
          title,
          url: `https://example.com/source-${i + 1}`,
        }))
      : [];
  return { stream: new MockAssistantStream(text), citations };
}
