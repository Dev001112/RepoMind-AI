"""LCEL chain that fills in the judgment-based Repository Knowledge fields
from already-extracted deterministic metadata. Uses a PydanticOutputParser
(not `.with_structured_output()`) deliberately -- the LLM handed in may be a
`RunnableWithFallbacks` (when an OpenRouter fallback is configured), which
doesn't expose `.with_structured_output()`; a plain prompt-parses-JSON chain
works over any Runnable.
"""

from pydantic import BaseModel, Field
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import Runnable

from app.ai.prompts.knowledge_enrichment_prompt import KNOWLEDGE_ENRICHMENT_PROMPT


class KnowledgeEnrichment(BaseModel):
    repository_type: str = Field(
        description="e.g. 'web application', 'CLI tool', 'library', 'ML/AI project'"
    )
    production_readiness: str = Field(description="one of: experimental, beta, stable")
    difficulty_level: str = Field(description="one of: beginner, intermediate, advanced")
    architecture_summary: str = Field(
        description="2-4 plain-language sentences on how the project is structured"
    )
    use_cases: list[str] = Field(description="3-5 concrete things someone would use this for")
    potential_applications: list[str] = Field(
        description="2-4 example projects/products someone could build with this"
    )
    performance_notes: list[str] = Field(
        description=(
            "0-3 short notes on likely performance characteristics/risks inferable from the "
            "stated facts (e.g. dependency choices, sync-vs-async framework, caching presence) "
            "-- empty list if there's nothing worth flagging, don't invent generic advice"
        )
    )


def build_knowledge_enrichment_chain(
    llm: Runnable[LanguageModelInput, BaseMessage],
) -> Runnable[dict, KnowledgeEnrichment]:
    parser = PydanticOutputParser(pydantic_object=KnowledgeEnrichment)
    prompt = KNOWLEDGE_ENRICHMENT_PROMPT.partial(format_instructions=parser.get_format_instructions())
    return prompt | llm | parser
