"""Prompt for the judgment-based Repository Knowledge fields -- the ones a
detector can't answer deterministically (architecture summary, use cases,
readiness, difficulty). See app.services.knowledge_builder.knowledge_builder
for why these, specifically, go through the LLM and nothing else does.
"""

from langchain_core.prompts import ChatPromptTemplate

KNOWLEDGE_ENRICHMENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a senior software engineer assessing an unfamiliar code repository for "
            "another engineer deciding whether to adopt it. Base your answer ONLY on the facts "
            "given below -- never invent a dependency, framework, or capability that isn't "
            "listed. Respond with ONLY the JSON object described here, no other text.\n\n"
            "{format_instructions}",
        ),
        ("human", "Repository facts:\n{context}"),
    ]
)
