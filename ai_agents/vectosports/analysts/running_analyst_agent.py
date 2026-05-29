"""Running analyst agent - specialist for biomechanical analysis of running."""

import logging

logger = logging.getLogger(__name__)

class RunningAnalystAgent:
    def __init__(self):
        from google.adk.agents.llm_agent import Agent
        from google.genai import types
        from ai_agents.vectosports.specialists.running_technique_specialist import running_technique_specialist

        self.agent = Agent(
            model='gemini-3-flash-preview',
            generate_content_config=types.GenerateContentConfig(
                temperature=0.0
            ),
            name='running_analyst_agent',
            description='Coordinator for running analysis. Routes to Running Technique Specialist.',
            instruction="""You are the Lead Running Analyst.

Your job is to route the analysis request to the correct sub-specialist based on the content of the request.

**Routing Rules:**
1.  **Running Technique:** For all requests regarding running technique, form, sprints, or distance running mechanics, transfer to the `running_technique_specialist`.

Simply identify the focus of the analysis and delegate to the appropriate expert.

**KEYPOINT COLOR REFERENCE:**
The video contains colored skeleton/keypoint overlays using the following color scheme:

*Skeleton Connections (Lines) - Differentiated by Body Side:*
- **Left Side** (Lado Esquerdo): Bright Blue (240, 100, 100) - Left arm and left leg connections
- **Right Side** (Lado Direito): Bright Red/Orange (100, 100, 240) - Right arm and right leg connections
- **Center/Head** (Cabeça): Bright Green (100, 240, 100) - Nose and head connections
- **Torso** (Tronco): Cyan (200, 200, 100) - Hip-to-hip and shoulder-to-shoulder connections

*Keypoint Dots (Individual Points) - Differentiated by Body Side:*
- **Center** (Nariz - Index 0): Bright Green (100, 240, 100) - Nose
- **Left Side** (Índices ímpares 1, 3, 5, 7, 9, 11, 13, 15): Bright Blue (240, 100, 100)
  - Left eye, left ear, left shoulder, left elbow, left wrist, left hip, left knee, left ankle
- **Right Side** (Índices pares 2, 4, 6, 8, 10, 12, 14, 16): Bright Red/Orange (100, 100, 240)
  - Right eye, right ear, right shoulder, right elbow, right wrist, right hip, right knee, right ankle

**IMPORTANT:** If a keypoint appears to be incorrectly positioned or tracking (e.g., a knee point appears in the wrong location), **disregard that keypoint** and rely on the visual evidence from the video instead.

Always respond in the language specified in the user message (e.g., 'Language: pt-br' for Portuguese). If not specified, default to English.""",
            sub_agents=[
                running_technique_specialist.agent
            ]
        )

    async def run(self, payload):
        logger.info(f"Running analyst agent received payload: {payload}")
        result = await self.agent.run(payload)
        logger.info(f"Running analyst agent returned result: {result}")
        return result

running_analyst_agent = RunningAnalystAgent()
