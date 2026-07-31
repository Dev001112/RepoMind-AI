"""Builds the final RepositoryKnowledge object from aggregated metadata.

Deterministic fields (languages, frameworks, dependencies, GPU/CUDA, docker,
install steps, folder structure, license, main entry point) are pure
assembly -- no LLM involved. A handful of judgment fields that genuinely
can't be extracted deterministically (architecture summary, use cases,
potential applications, production readiness, difficulty level) are filled
in by one best-effort LLM call; if that call fails for any reason (no
provider configured, quota, network, malformed output), those fields are
simply left None/empty rather than failing the whole pipeline.
"""

import logging
import uuid

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from app.ai.chains.knowledge_enrichment_chain import (
    KnowledgeEnrichment,
    build_knowledge_enrichment_chain,
)
from app.models.schemas.knowledge import RepositoryKnowledge

logger = logging.getLogger(__name__)

_MAX_CONTEXT_ITEMS = 30  # keep the enrichment prompt compact


class KnowledgeBuilder:
    def __init__(self, chat_model: Runnable[LanguageModelInput, BaseMessage] | None = None) -> None:
        self.chat_model = chat_model

    def build(self, repository_id: uuid.UUID, metadata: dict) -> RepositoryKnowledge:
        dependencies = metadata.get("dependencies") or {}
        libraries = sorted(dependencies.keys())

        enrichment = self._enrich(metadata) if self.chat_model is not None else None

        return RepositoryKnowledge(
            repository_id=repository_id,
            name=metadata.get("name"),
            description=metadata.get("description"),
            repository_type=enrichment.repository_type if enrichment else None,
            languages=metadata.get("languages") or [],
            frameworks=metadata.get("frameworks") or [],
            libraries=libraries,
            dependencies=dependencies,
            gpu_required=metadata.get("gpu_required"),
            cuda_required=metadata.get("cuda_required"),
            docker_support=metadata.get("docker_support"),
            installation_steps=metadata.get("installation_steps") or [],
            package_managers=metadata.get("package_managers") or [],
            production_readiness=enrichment.production_readiness if enrichment else None,
            difficulty_level=enrichment.difficulty_level if enrichment else None,
            architecture_summary=enrichment.architecture_summary if enrichment else None,
            folder_structure=metadata.get("folder_structure") or {},
            main_entry_point=metadata.get("main_entry_point"),
            use_cases=enrichment.use_cases if enrichment else [],
            potential_applications=enrichment.potential_applications if enrichment else [],
            license=metadata.get("license"),
            security_findings=metadata.get("security_findings") or [],
            performance_notes=enrichment.performance_notes if enrichment else [],
            dependency_graph=metadata.get("dependency_graph") or {},
        )

    def _enrich(self, metadata: dict) -> KnowledgeEnrichment | None:
        try:
            chain = build_knowledge_enrichment_chain(self.chat_model)
            return chain.invoke({"context": self._build_context(metadata)})
        except Exception:
            logger.warning(
                "Knowledge enrichment LLM call failed; leaving judgment fields empty",
                exc_info=True,
            )
            return None

    def _build_context(self, metadata: dict) -> str:
        dependencies = metadata.get("dependencies") or {}
        folder_structure = metadata.get("folder_structure") or {}
        lines = [
            f"Name: {metadata.get('name') or 'unknown'}",
            f"Description: {metadata.get('description') or 'none given'}",
            f"Languages: {', '.join(metadata.get('languages') or []) or 'none detected'}",
            f"Frameworks: {', '.join(metadata.get('frameworks') or []) or 'none detected'}",
            "Notable dependencies: "
            + (", ".join(sorted(dependencies.keys())[:_MAX_CONTEXT_ITEMS]) or "none detected"),
            f"Package managers: {', '.join(metadata.get('package_managers') or []) or 'none detected'}",
            f"Docker support: {metadata.get('docker_support')}",
            f"GPU required: {metadata.get('gpu_required')}, CUDA required: {metadata.get('cuda_required')}",
            "Top-level structure: "
            + (", ".join(list(folder_structure.keys())[:_MAX_CONTEXT_ITEMS]) or "unknown"),
            f"Main entry point: {metadata.get('main_entry_point') or 'unknown'}",
            "Static security scan findings: "
            + ("; ".join(metadata.get("security_findings") or []) or "none flagged"),
        ]
        return "\n".join(lines)
