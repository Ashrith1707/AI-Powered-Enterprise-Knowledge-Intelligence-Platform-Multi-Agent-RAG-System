"""Builds the grounded prompt: numbered context blocks + citation rules."""
from app.rag.retriever import RetrievedChunk

SYSTEM_PROMPT = """You are an enterprise knowledge assistant. Answer ONLY from the
provided context blocks. Rules:
1. Cite every factual statement with the block marker, e.g. [1] or [2][3].
2. If the context does not contain the answer, say exactly:
   "The knowledge base does not contain enough information to answer this."
3. Never invent facts, numbers, or sources.
4. Be concise and professional."""


# Adaptive prompting: the query type picks the answer-shape instruction.
STYLE_HINTS = {
    "factual": "Answer directly and concisely.",
    "list": "Answer as a markdown bullet list, one cited fact per bullet.",
    "summary": "Answer as a short structured summary with a heading per theme.",
    "comparison": "Answer as a markdown comparison table where possible.",
}


class PromptBuilder:
    def build(self, question: str, chunks: list[RetrievedChunk],
              query_type: str = "factual") -> str:
        context_blocks = "\n\n".join(
            f"[{i}] (source: {c.document_name}, page {c.page_number})\n{c.text}"
            for i, c in enumerate(chunks, start=1)
        )
        style = STYLE_HINTS.get(query_type, STYLE_HINTS["factual"])
        return (f"{SYSTEM_PROMPT}\n5. {style}\n\n"
                f"CONTEXT:\n{context_blocks}\n\n"
                f"QUESTION: {question}\n\n"
                f"ANSWER (with [n] citations):")
