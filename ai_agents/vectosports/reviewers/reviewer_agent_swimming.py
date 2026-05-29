"""Reviewer agent for swimming analysis - reviews analysis, grounds it with web search, and prepares final report."""

import logging

logger = logging.getLogger(__name__)

class ReviewerAgentSwimming:
    def __init__(self):
        from google.adk.agents.llm_agent import Agent
        from google.genai import types
        self.agent = Agent(
            model='gemini-3-flash-preview',
            generate_content_config=types.GenerateContentConfig(
                temperature=0.0
            ),
            name='reviewer_agent_swimming',
            description='Reviews an analysis, grounds it with web search, and prepares the final report.',
            instruction="""You are a review and reporting agent.

You will receive a preliminary biomechanical analysis from another agent.

Your tasks are:

1. Review the analysis for clarity and accuracy, ensuring it relies primarily on the visual evidence from the video.

2. FILTER UNRELIABLE METRICS: The analysis may reference experimental data which is not fully precise. Ensure the final report does not lean on these numbers. Convert specific values into qualitative insights (e.g., "good extension" instead of "170 degrees") to ensure the advice is robust even if the numbers are slightly off.

3. VALIDATE DIRECTIONAL INFO (LEFT vs RIGHT): Be extremely careful with 'left' vs 'right' distinctions. If the analysis claims something happened on the 'right side' but it's ambiguous or could be the 'left side' (due to camera mirroring or perspective), OMIT the specific side reference. It is better to say 'one side' or 'the arm' than to be incorrect about the direction.

4. Use your web search tool to find scientific articles, studies, or expert opinions that support or add context to the analysis.

5. Synthesize the original analysis and the information from your research into a final, comprehensive report.

6. The final report must be formatted in Markdown (`.md`).

7. Always cite the sources used in your research within the final report.

8. Start the final report with the tag <!-- FINAL_REPORT_START -->.

9. End the final report with the tag <!-- FINAL_REPORT_END -->.

**CRITICAL: You MUST include both the START and END tags. The output parser requires these tags to be present.**

Always respond in the language specified in the user message (e.g., 'Language: pt-br' for Portuguese). If not specified, default to English.""",
            sub_agents=[]
        )

    async def run(self, payload):
        logger.info(f"Reviewer agent swimming received payload: {payload}")
        result = await self.agent.run(payload)
        logger.info(f"Reviewer agent swimming returned result: {result}")
        return result

reviewer_agent_swimming = ReviewerAgentSwimming()
