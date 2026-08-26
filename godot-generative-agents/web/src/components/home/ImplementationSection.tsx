import { CodeBlock } from "./CodeBlock";
import { SectionHeading } from "./SectionHeading";
import checkOutBookCode from "./snippets/check_out_book.py?raw";
import checkOutBookTool from "./snippets/check_out_book.tool.json?raw";
import checkOutBookGateCode from "./snippets/check_out_book_gate.py?raw";
import gateCode from "./snippets/gate.py?raw";
import myVerbCode from "./snippets/my_verb.py?raw";

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
  gateExample: {
    code: checkOutBookGateCode,
    lang: "python",
    caption:
      "godot-generative-agents/backend/actions.py — CheckOutBook's gate and effects, verbatim; the constructor and its _match_book helper are cut, which is why self.book and self.character appear unassigned",
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
  myVerb: {
    // Kept for the commented-out "Adding your own verb" subsection (#880/#884).
    code: myVerbCode,
    lang: "python",
    caption: "a commented template for a custom verb",
  },
} satisfies Record<string, { code: string; lang: "python" | "json"; caption: string }>;

/**
 * "The text-adventure engine" — the section that makes the Abstract's central
 * claim checkable. The Abstract says the model never mutates state directly;
 * this is where a reader sees the five lines that enforce it, one real action
 * passing through them, and how a verb becomes a tool the model can call —
 * all inside the classical `text_adventure_games` library the sim runs on.
 *
 * "Adding your own verb" is commented out below until #880 (Run locally) ships
 * with the public codebase (#884) — a fill-in-the-blank verb template is not
 * useful until readers can actually clone and run the engine.
 */
export function ImplementationSection() {
  return (
    <section className="nrf-section">
      <div className="nrf-container">
        <div className="nrf-narrow">
          <SectionHeading id="engine" level={2} className="nrf-title nrf-title-3 nrf-centered">
            The text-adventure engine
          </SectionHeading>
          <div className="nrf-content nrf-justified">
            <p>
              The simulation runs on <code>text_adventure_games</code>, a classical text-adventure
              engine — rooms, items, characters, and a keyword parser — built from{" "}
              <a href="https://interactive-fiction-class.org/homeworks/text-adventure-game/text-adventure-game.html">
                Chris Callison-Burch's CIS 7000 – <em>Interactive Fiction and Text Generation</em>{" "}
                course materials
              </a>{" "}
              and extended until a language model could drive a character through it. The engine's
              design predates the agents and knows nothing about them, which is precisely what makes
              the gate below worth trusting: it was not built to contain a model, so it has no
              special case that lets one through.
            </p>

            <SectionHeading id="the-gate" level={3} className="nrf-title nrf-title-4">
              The precondition gate
            </SectionHeading>
            <p>
              Every action a character takes passes through five lines. An action checks its
              preconditions; only if they hold does it apply its effects.
            </p>
            <CodeBlock {...SNIPPETS.gate} />
            <p>
              Every action in the engine subclasses this, and so does every world-initiated reflex.
              There is no second path. A decision from a language model arrives as a command string,
              is parsed into one of these objects, and then either passes or does not — the model is
              never holding the pen.
            </p>
            <p>
              Here is a real one — the verb a student uses to borrow a library book from the shelf,
              which you will meet again in a moment from the other side:
            </p>
            <CodeBlock {...SNIPPETS.gateExample} />
            <p>
              Preconditions are ordinary predicates and effects are ordinary mutation. There is no
              rules engine to misconfigure and nothing to reach around. A rejected action is not
              silent either: the reason passed to <code>parser.fail</code> becomes a failure memory,
              and can trigger the plan revision described above — so the refusal is information, not
              a dead end.
            </p>

            <SectionHeading id="verb-to-tool" level={3} className="nrf-title nrf-title-4">
              From verb to tool
            </SectionHeading>
            <p>
              The model is not asked "what do you do?" and parsed hopefully. It receives one typed
              tool per verb, derived from the same registry the gate reads. That is the same verb
              from the inside. From the outside, its declaration is all the engine needs to build
              the tool the model is offered:
            </p>
            <div className="nrf-panes">
              <CodeBlock {...SNIPPETS.declaration} />
              <CodeBlock {...SNIPPETS.tool} />
            </div>
            <p>Three things follow from that declaration.</p>
            <p>
              <strong>The menu is curated by place.</strong> Declaring an affordance means the verb
              is offered only where something carrying that property is in scope. Of the eleven
              verbs this cast declares, seven survive the affordance check at the book stacks;{" "}
              <em>study</em>, <em>eat</em>, <em>activate</em> and <em>deactivate</em> are simply
              absent, because nothing there affords them.
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

            {/* TODO(#880): restore "Adding your own verb" when the Run locally
                section ships with the public codebase (#884). The subsection
                (heading id="your-own-verb", myVerb snippet, custom_actions
                prose, docs link) and its TOC entry in toc.ts come back
                together — a fill-in-the-blank verb is only useful once readers
                can clone and run the engine.

            <SectionHeading id="your-own-verb" level={3} className="nrf-title nrf-title-4">
              Adding your own verb
            </SectionHeading>
            <p>
              The framework exists so that other people can build simulations on it, which means
              adding to the world has to be cheap. A new verb is one class:
            </p>
            <CodeBlock {...SNIPPETS.myVerb} />
            <p>
              Pass it to the game as <code>custom_actions=[MyVerb]</code> and it becomes three
              things at once: a command a human player can type, an option a scripted NPC can take,
              and a typed tool in every agent's menu — offered only where the declared affordance is
              in scope. That last one is the engine's default wiring; a simulation that curates its
              own verb list, as this one does, names the verb there instead. The full engine
              reference, generated from these same sources, is at{" "}
              <a href={`${import.meta.env.BASE_URL}docs/`}>the documentation site</a>.
            </p>
            */}
          </div>
        </div>
      </div>
    </section>
  );
}
