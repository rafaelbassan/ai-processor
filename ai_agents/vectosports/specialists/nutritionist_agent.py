"""Nutritionist agent - provides sports nutrition advice based on athlete's profile."""

import logging

logger = logging.getLogger(__name__)

class NutritionistAgent:
    def __init__(self):
        from google.adk.agents.llm_agent import Agent
        from google.genai import types
        self.agent = Agent(
            model='gemini-3-flash-preview',
            generate_content_config=types.GenerateContentConfig(
                temperature=0.1
            ),
            name='nutritionist_agent',
            description='Provides sports nutrition advice based on athlete\'s profile and goals.',
            instruction="""You are a specialist in sports nutrition.

Based on the athlete's profile (name, age, weight, height, sport, training
load, goals), provide a detailed nutritional plan.

- Use your web search tool to find the latest scientific recommendations to
  support your advice.

- The plan should cover pre-training, during-training, and post-training
  nutrition.

- Include recommendations for hydration and, if relevant, supplementation.

- Explain the reasoning behind your recommendations.""",
            sub_agents=[]
        )

    async def run(self, payload):
        logger.info(f"Nutritionist agent received payload: {payload}")
        result = await self.agent.run(payload)
        logger.info(f"Nutritionist agent returned result: {result}")
        return result

nutritionist_agent = NutritionistAgent()
