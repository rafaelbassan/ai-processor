"""Performance analyst agent - analyzes athlete performance based on competition results."""

import logging

logger = logging.getLogger(__name__)

class PerformanceAnalystAgent:
    def __init__(self):
        from google.adk.agents.llm_agent import Agent
        from google.genai import types
        self.agent = Agent(
            model='gemini-3-flash-preview',
            generate_content_config=types.GenerateContentConfig(
                temperature=0.0
            ),
            name='performance_analyst_agent',
            description='Analyzes athlete performance based on competition results and historical data.',
            instruction="""You are a specialist in sports performance analysis.

Your task is to analyze an athlete's performance based on their competition
results and training data.

- Show their evolution over time.

- Compare their progress against expected performance curves for their age,
  sport, and level.

- Highlight strengths and areas for improvement based on the data trends.

- Present your analysis in a clear, easy-to-understand report.""",
            sub_agents=[]
        )

    async def run(self, payload):
        logger.info(f"Performance analyst agent received payload: {payload}")
        result = await self.agent.run(payload)
        logger.info(f"Performance analyst agent returned result: {result}")
        return result

performance_analyst_agent = PerformanceAnalystAgent()
