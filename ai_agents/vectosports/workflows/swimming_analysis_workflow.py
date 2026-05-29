"""Swimming analysis workflow - two-step workflow for swimming sports."""

import logging

logger = logging.getLogger(__name__)

class SwimmingAnalysisWorkflow:
    def __init__(self):
        from google.adk.agents.sequential_agent import SequentialAgent
        from ai_agents.vectosports.analysts.swimming_analyst_agent import swimming_analyst_agent
        from ai_agents.vectosports.reviewers.reviewer_agent_swimming import reviewer_agent_swimming
        
        from ai_agents.vectosports.coaches.coach_agent import CoachAgent
        
        coach_agent = CoachAgent()
        
        self.workflow = SequentialAgent(
            name='swimming_analysis_workflow',
            description='A three-step workflow for swimming: 1. Specialist Analysis, 2. Review and Reporting, 3. Coach Tips Generation.',
            sub_agents=[
                swimming_analyst_agent.agent,
                reviewer_agent_swimming.agent,
                coach_agent.agent
            ]
        )

    async def run(self, payload):
        logger.info(f"Swimming analysis workflow received payload: {payload}")
        result = await self.workflow.run(payload)
        logger.info(f"Swimming analysis workflow returned result: {result}")
        return result

swimming_analysis_workflow = SwimmingAnalysisWorkflow()
