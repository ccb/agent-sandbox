"""Compare keyword-overlap vs semantic (embedding) memory retrieval (issue #102).

Wiring an embedding client into the sim (``run_simulation --embeddings``) doesn't
change the *replay*: the deterministic mock brain decides from location alone and
ignores the retrieved-memory block, so the exported frames are byte-identical with
or without embeddings (that invariant is locked down by
``tests/test_memory_wiring.py``). The payoff only shows up once a real LLM brain
reasons over the retrieved memories (NEXT-STEPS Phase A).

So how do we tell whether semantic retrieval is even *worth* turning on before that
brain exists? We measure retrieval quality **directly**: accrue a real memory stream
for each resident (their own actions + perceptions of co-located neighbors), then
ask the same question two ways -- "which memories does keyword overlap surface for
this situation, and which does cosine similarity surface?" -- and report where the
two diverge. This is the believability question from issue #102 made concrete:
*does semantic recall surface different (hopefully better) memories than keyword
overlap for residents?*

This is a **manual research tool**, not part of the replay pipeline or CI. It needs
no maze assets (``build_world`` alone, no ``setup.sh``) and runs fully offline.

    # Meaningful comparison with a real local model (model2vec):
    uv sync --extra embeddings
    uv run python -m gen_agents.compare_retrieval --embeddings local

    # Other knobs:
    uv run python -m gen_agents.compare_retrieval --steps 20 --top-k 4 --examples 5
    uv run python -m gen_agents.compare_retrieval --resident "Isabella Rodriguez" \
        --query "who likes coffee and conversation?"

Note on the mock backend: ``MockEmbeddingClient`` is a hashed bag-of-words, so it
has **no real semantics** -- two memories are "similar" only when they literally
share words. It will still diverge from keyword overlap (cosine over word *counts*
ranks differently than the share-of-query-words *fraction* that
``relevance_score`` computes), but that divergence is a scoring-function artifact,
not semantic insight. A real backend (``--embeddings local``) is what adds genuine
semantic similarity -- synonyms and paraphrase that share no words -- on top.
"""

import argparse

from text_adventure_games.embedding_client import (
    EmbeddingConfig,
    MockEmbeddingClient,
    create_embedding_client,
)

from .build_world import PERSONAS, build_world
from .smallville_agents import attach_agents, observe_and_decide, remember_outcome


def make_embedding_client(provider: str):
    """Build the embedding backend to compare against keyword overlap.

    Unlike the sim's ``resolve_embedding_client`` (which returns ``None`` to fall
    back to keyword overlap), this tool *needs* a client -- there is nothing to
    compare without one. So when the requested backend can't be created (e.g. the
    ``embeddings`` extra isn't installed), fall back to the deterministic
    :class:`MockEmbeddingClient` and say so loudly, rather than degrading to a
    keyword-vs-keyword no-op.
    """
    try:
        return create_embedding_client(EmbeddingConfig(provider=provider))
    except (ImportError, ValueError) as exc:
        print(
            f"Note: could not create the '{provider}' backend ({exc}).\n"
            "Falling back to the deterministic MockEmbeddingClient (a hashed "
            "bag-of-words), so the two columns will look nearly identical. For a "
            "real comparison: `uv sync --extra embeddings` then `--embeddings local`.\n"
        )
        return MockEmbeddingClient()


def accrue_memories(game, chars, num_steps: int) -> None:
    """Drive the mock decision loop so residents build up a real memory stream.

    This is ``run_simulation.simulate``'s memory-relevant core with the tile/path
    machinery dropped (the probe never renders sprites): each step every resident
    perceives co-located neighbors (:meth:`AgentMemory.ingest_events`), and an
    idle resident decides + records the outcome via the same ``smallville_agents``
    helpers the real loop uses. ``travel`` resolves the logical move immediately,
    so a resident reaches its hub and settles into ``perform`` within a couple of
    steps; the remaining steps let every co-located arrival be perceived.
    """
    order = [p["name"] for p in PERSONAS]
    settled: set[str] = set()
    for step in range(num_steps):
        game.turn = step
        for name in order:
            char = chars[name]
            if name in settled:
                # observe_and_decide() would perceive for us; settled residents
                # skip it, so perceive explicitly to keep folding in neighbors.
                char.agent.memory.ingest_events(game, char)
                continue
            command = observe_and_decide(game, char, step)
            if command and game.parser.parse_command(command, actor=char):
                remember_outcome(char, command, step)
                if command.startswith("perform"):
                    settled.add(name)


def _retrieve_both(memory, client, query: str, top_k: int, turn: int):
    """Top-``top_k`` memories for *query* under keyword overlap and under *client*.

    Both retrievals are read-only (``touch=False``) over the same stream at the
    same *turn*, so recency and importance are held fixed and the only thing that
    can move a memory between the two lists is the relevance term. Swapping
    ``memory.embedding_client`` is what flips relevance between keyword overlap
    (``None``) and cosine similarity (the client); it's restored afterwards.
    """
    saved = memory.embedding_client
    try:
        memory.embedding_client = None
        keyword = memory.retrieve(query, turn=turn, max_records=top_k, touch=False)
        memory.embedding_client = client
        semantic = memory.retrieve(query, turn=turn, max_records=top_k, touch=False)
    finally:
        memory.embedding_client = saved
    return keyword, semantic


def compare(game, chars, client, *, query, top_k, turn, only=None):
    """Compare retrieval for every resident (or just *only*) at *turn*.

    Returns one dict per resident that has *more* memories than ``top_k`` (so the
    two methods are actually choosing a subset -- residents with few memories
    return the same full set and tell us nothing about ranking quality).
    """
    names = [only] if only else [p["name"] for p in PERSONAS]
    results = []
    for name in names:
        char = chars[name]
        memory = char.agent.memory
        if len(memory.records) <= top_k:
            continue
        this_query = query if query is not None else game.describe_for(char)
        keyword, semantic = _retrieve_both(memory, client, this_query, top_k, turn)
        kw_ids = [r.id for r in keyword]
        sem_ids = [r.id for r in semantic]
        results.append(
            {
                "name": name,
                "query": this_query,
                "keyword": keyword,
                "semantic": semantic,
                "same_set": set(kw_ids) == set(sem_ids),
                "same_order": kw_ids == sem_ids,
            }
        )
    return results


def _format_block(records, other_ids, indent="    ") -> list[str]:
    """Render one column's memories, marking those absent from the other column.

    ``*`` flags a memory unique to this list (surfaced by one method but not the
    other); ``-`` marks a memory both methods agreed on.
    """
    other = set(other_ids)
    lines = []
    for record in records:
        mark = "-" if record.id in other else "*"
        bullet = f"[{record.kind.value}, turn {record.created_turn}] {record.text}"
        lines.append(f"{indent}{mark} {bullet}")
    return lines


def report(results, *, client, num_steps, top_k, query, examples: int) -> None:
    """Print the summary counts and a few diverging examples side by side."""
    backend = type(client).__name__
    query_desc = f'fixed query "{query}"' if query else "each resident's observation"
    print(f"Retrieval comparison: keyword overlap vs semantic ({backend})")
    print(
        f"Accrued memories over {num_steps} mock steps; top-{top_k} per query; "
        f"query = {query_desc}.\n"
    )

    if not results:
        print(
            "No resident accrued more than top-k memories, so keyword and semantic "
            "return the same full set. Try more --steps or a smaller --top-k."
        )
        return

    diff_set = [r for r in results if not r["same_set"]]
    reorder = [r for r in results if r["same_set"] and not r["same_order"]]
    identical = [r for r in results if r["same_order"]]
    print("Summary:")
    print(f"  residents compared (>{top_k} memories):  {len(results)}")
    print(f"  different set of memories surfaced:      {len(diff_set)}")
    print(f"  same set, different ranking:             {len(reorder)}")
    print(f"  identical top-{top_k}:                          {len(identical)}\n")

    # Lead with set-differences (the strongest signal), then reorderings.
    shown = (diff_set + reorder)[:examples]
    if not shown:
        print("Keyword and semantic agreed on every resident's top-k (set + order).")
        return
    print(f"Examples where they diverge (showing {len(shown)}):")
    print("  '*' = surfaced by only this method, '-' = surfaced by both.\n")
    for r in shown:
        flat_query = " ".join(r["query"].split())
        snippet = flat_query[:70] + ("..." if len(flat_query) > 70 else "")
        print(f"─── {r['name']} ───")
        print(f"    query: {snippet}")
        print("  keyword overlap:")
        print("\n".join(_format_block(r["keyword"], [x.id for x in r["semantic"]])))
        print("  semantic:")
        print("\n".join(_format_block(r["semantic"], [x.id for x in r["keyword"]])))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare keyword-overlap vs semantic memory retrieval for "
        "the Smallville residents (issue #102). Offline; no maze assets needed."
    )
    parser.add_argument(
        "--embeddings",
        default="local",
        metavar="PROVIDER",
        help="embedding backend to compare against keyword overlap "
        "(local | mock | sentence-transformers | openai; default: local). "
        "Falls back to the mock backend if the chosen one isn't installed.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=12,
        help="mock steps to accrue memories before comparing (default: %(default)s)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="how many memories each method surfaces per query (default: %(default)s)",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="probe every resident with this fixed situation instead of their own "
        "current observation (handy for exploring, e.g. 'who is at the cafe?')",
    )
    parser.add_argument(
        "--resident",
        default=None,
        help="limit the comparison to one resident by full name",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=3,
        help="how many diverging residents to show in detail (default: %(default)s)",
    )
    args = parser.parse_args()

    client = make_embedding_client(args.embeddings)

    # Accrue under keyword relevance (embedding_client=None) so both compared
    # methods start from the same recency state; the comparison then swaps the
    # client in per-retrieval. build_world() needs no maze assets.
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    accrue_memories(game, chars, args.steps)

    results = compare(
        game,
        chars,
        client,
        query=args.query,
        top_k=args.top_k,
        turn=args.steps,
        only=args.resident,
    )
    report(
        results,
        client=client,
        num_steps=args.steps,
        top_k=args.top_k,
        query=args.query,
        examples=args.examples,
    )


if __name__ == "__main__":
    main()
