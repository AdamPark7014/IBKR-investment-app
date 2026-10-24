from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping

DISALLOWED = (
    'Do not invent prices, fills, or news.',
    'Do not recommend LIVE orders or leverage.',
    'Do not promise returns, alpha, or income.',
    'Only restate and explain the provided FACTS JSON.',
)


@dataclass
class PromptPack:
    name: str = 'ibtrader-brief-v1'
    model: str = 'claude-haiku-5-5'
    max_tokens: int = 400
    temperature: float = 0.0
    effort: str = 'low'
    language: str = 'es'
    tone: str = 'claro, directo, sin jerga innecesaria'
    audience: str = 'operador paper que quiere entender el estado en 30 segundos'
    proceso: str = 'ibtrader-brief'
    system_template: str = (
        'Eres el coach de triage de ibtrader. Idioma={language}. Tono={tone}. '
        'Audiencia={audience}. Explica SOLO los FACTS. '
        'Formato: 1) Estado en 1 frase.\n2) 3 bullets de datos.\n3) 1 accion paper sugerida o ESPERAR.\n'
        'Prohibido: {disallowed}'
    )
    user_template: str = (
        'FACTS:\n{facts_json}\n\nResponde en {language}.'
    )
    disallowed: tuple[str, ...] = DISALLOWED
    extra: Dict[str, Any] = field(default_factory=dict)

    def render_system(self) -> str:
        return self.system_template.format(
            language=self.language, tone=self.tone, audience=self.audience,
            disallowed='; '.join(self.disallowed),
        )

    def render_user(self, facts: Mapping[str, Any]) -> str:
        compact = json.dumps(facts, ensure_ascii=False, separators=(',', ':'))
        return self.user_template.format(facts_json=compact, language=self.language)

    def messages(self, facts: Mapping[str, Any]) -> List[Dict[str, str]]:
        return [
            {'role': 'system', 'content': self.render_system()},
            {'role': 'user', 'content': self.render_user(facts)},
        ]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['disallowed'] = list(self.disallowed)
        return d


def default_pack(**overrides: Any) -> PromptPack:
    p = PromptPack()
    for k, v in overrides.items():
        if hasattr(p, k):
            setattr(p, k, v)
    return p


__all__ = ['PromptPack', 'default_pack', 'DISALLOWED']