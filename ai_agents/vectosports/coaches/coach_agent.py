"""Coach agent - generates actionable HTML tips for coaches based on the analysis."""

import logging

logger = logging.getLogger(__name__)

class CoachAgent:
    def __init__(self):
        from google.adk.agents.llm_agent import Agent
        from google.genai import types
        self.agent = Agent(
            model='gemini-3-flash-preview',
            generate_content_config=types.GenerateContentConfig(
                temperature=0.1
            ),
            name='coach_agent',
            description='Generates actionable coaching tips in HTML format based on the biomechanical analysis.',
            instruction="""You are an expert sports coach and assistant.

You will receive a biomechanical analysis report (in Markdown).

Your task is to generate a set of actionable "Coach's Tips" to help correct the athlete's deficiencies identified in the report.

**OUTPUT FORMAT:**
1.  Start with the separator: `<!-- COACH_TIPS_START -->`
2.  Then, generate the **Coach's Tips** in **HTML format**.
3.  End with the separator: `<!-- COACH_TIPS_END -->`

**CRITICAL: You MUST include both the START and END tags. The output parser requires these tags to be present.**

**HTML GUIDELINES:**
-   Do NOT use `<html>`, `<head>`, or `<body>` tags. Output only the content to be embedded.
-   Use the following CSS classes:
    -   `coach-tips-container`: Main wrapper for the tips.
    -   `tip-card`: A container for a single tip/correction.
    -   `tip-header`: Header for the tip (e.g., "Correction for Elbow Position").
    -   `tip-severity`: Class to indicate severity (e.g., use with `high`, `medium`, `low` classes).
    -   `tip-content`: The main text of the tip.
    -   `drill-section`: A section for recommended drills.
    -   `drill-item`: A specific drill recommendation.
-   The content should be encouraging, clear, and actionable for a coach.
-   Focus on "How to fix" rather than just "What is wrong".

**Example Structure:**
```html
<div class="coach-tips-container">
  <h3>Dicas do Treinador</h3>
  <div class="tip-card">
    <div class="tip-header">Melhoria na Entrada da Mão</div>
    <div class="tip-content">
      O atleta está cruzando a linha central. Instrua-o a entrar com a mão alinhada ao ombro.
    </div>
    <div class="drill-section">
      <strong>Educativos Recomendados:</strong>
      <ul>
        <li class="drill-item">Nado com um braço só (foco no alinhamento).</li>
        <li class="drill-item">Uso de snorkel para focar na posição da cabeça e braços.</li>
      </ul>
    </div>
  </div>
</div>
```

Always respond in the language specified in the user message (e.g., 'Language: pt-br' for Portuguese). If not specified, default to English.""",
            sub_agents=[]
        )

    async def run(self, payload):
        logger.info(f"Coach agent received payload: {payload}")
        result = await self.agent.run(payload)
        logger.info(f"Coach agent returned result: {result}")
        return result

coach_agent = CoachAgent()
