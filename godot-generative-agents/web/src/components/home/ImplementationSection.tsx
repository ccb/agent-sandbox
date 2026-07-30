import { CodeBlock } from "./CodeBlock";
import checkOutBookCode from "./snippets/check_out_book.py?raw";
import checkOutBookTool from "./snippets/check_out_book.tool.json?raw";
import dropCode from "./snippets/drop.py?raw";
import gateCode from "./snippets/gate.py?raw";
import napCode from "./snippets/nap.py?raw";

/**
 * Every snippet on the page, loaded from the real files under snippets/.
 *
 * They are files rather than string literals so that ONE set of bytes serves
 * both sides: Vite's `?raw` hands them to React here, and
 * tests/test_landing_snippets.py reads the same files to pin them against the
 * engine source they quote. `caption` names the source file rather than linking
 * to it — the standalone repository is not public until #884.
 */
export const SNIPPETS = {
  gate: {
    code: gateCode,
    lang: "python",
    caption: "text_adventure_games/reactions.py — GatedEffect.__call__, verbatim",
  },
  drop: {
    code: dropCode,
    lang: "python",
    caption:
      "text_adventure_games/actions/things.py — abridged: docstrings and one duplicate branch removed",
  },
  declaration: {
    code: checkOutBookCode,
    lang: "python",
    caption: "godot-generative-agents/backend/actions.py — the declaration",
  },
  tool: {
    code: checkOutBookTool,
    lang: "json",
    caption: "the tool as generated for an agent in Van Pelt — Book Stacks",
  },
  nap: {
    code: napCode,
    lang: "python",
    caption: "a complete custom verb",
  },
} satisfies Record<string, { code: string; lang: "python" | "json"; caption: string }>;

/**
 * "Implementation" — the section that makes the Abstract's central claim
 * checkable. The Abstract says the model never mutates state directly; this is
 * where a reader sees the five lines that enforce it, one real action passing
 * through them, how a verb becomes a tool the model can call, and what writing
 * their own verb would take.
 */
export function ImplementationSection() {
  return (
    <section className="nrf-section">
      <div className="nrf-container">
        <div className="nrf-narrow">
          <h2 className="nrf-title nrf-title-3 nrf-centered" id="implementation">
            Implementation
          </h2>
          <div className="nrf-content nrf-justified">
            <p>
              The simulation runs on <code>text_adventure_games</code>, a classical text-adventure
              engine — rooms, items, characters, and a keyword parser — extended until a language
              model could drive a character through it. The engine's design predates the agents and
              knows nothing about them, which is precisely what makes the gate below worth trusting:
              it was not built to contain a model, so it has no special case that lets one through.
            </p>

            <h3 className="nrf-title nrf-title-4" id="the-gate">
              The precondition gate
            </h3>
            <p>
              Every change to the world passes through five lines. An action checks its
              preconditions; only if they hold does it apply its effects.
            </p>
            <CodeBlock {...SNIPPETS.gate} />
            <p>
              Every action in the engine subclasses this, and so does every world-initiated reflex.
              There is no second path. A decision from a language model arrives as a command string,
              is parsed into one of these objects, and then either passes or does not — the model is
              never holding the pen.
            </p>
            <p>Here is a real one, with its docstrings trimmed away:</p>
            <CodeBlock {...SNIPPETS.drop} />
            <p>
              Preconditions are ordinary predicates and effects are ordinary mutation. There is no
              rules engine to misconfigure and nothing to reach around. A rejected action is not
              silent either: the reason passed to <code>parser.fail</code> becomes a failure memory,
              and can trigger the plan revision described above — so the refusal is information, not
              a dead end.
            </p>

            <h3 className="nrf-title nrf-title-4" id="verb-to-tool">
              From verb to tool
            </h3>
            <p>
              The model is not asked "what do you do?" and parsed hopefully. It receives one typed
              tool per verb, derived from the same registry the gate reads. This declaration is the
              whole definition of the library's checkout verb:
            </p>
            <div className="nrf-panes">
              <CodeBlock {...SNIPPETS.declaration} />
              <CodeBlock {...SNIPPETS.tool} />
            </div>
            <p>Three things follow from that declaration.</p>
            <p>
              <strong>The menu is curated by place.</strong> Declaring an affordance means the verb
              is offered only where something carrying that property is in scope. Standing at the
              book stacks, this agent's menu is seven verbs; <em>study</em>, <em>eat</em>,{" "}
              <em>activate</em> and <em>deactivate</em> are simply absent, because nothing there
              affords them. The cast's full list runs to eleven.
            </p>
            <p>
              <strong>The arguments are bounded by perception.</strong> The typed <code>item</code>{" "}
              slot resolves to an enumeration of what this character can actually see, rebuilt for
              every decision. A book in another library is not a choice the model is able to express
              — the same perception window described above, reaching all the way into the shape of
              the tool call.
            </p>
            <p>
              <strong>Being offered is still not permission.</strong> The place-check runs a second
              time inside <code>check_preconditions</code>, and the possession and state checks run
              after it. Narrowing the menu is a convenience for the model; the gate remains the only
              authority over the world.
            </p>

            <h3 className="nrf-title nrf-title-4" id="your-own-verb">
              Adding your own verb
            </h3>
            <p>
              The framework exists so that other people can build simulations on it, which means
              adding to the world has to be cheap. A new verb is one class:
            </p>
            <CodeBlock {...SNIPPETS.nap} />
            <p>
              Pass it to the game as <code>custom_actions=[Nap]</code> and it becomes three things
              at once: a command a human player can type, an option a scripted NPC can take, and a
              typed tool in every agent's menu — offered only where there is a bench to sit on. The
              full engine reference, generated from these same sources, is at{" "}
              <a href="docs/">the documentation site</a>.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
