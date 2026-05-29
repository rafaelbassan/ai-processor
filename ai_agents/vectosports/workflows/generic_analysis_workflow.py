"""Generic analysis workflow - two-step workflow for non-swimming sports."""

import logging

logger = logging.getLogger(__name__)

class GenericAnalysisWorkflow:
    def __init__(self):
        from google.adk.agents.sequential_agent import SequentialAgent
        from ai_agents.vectosports.analysts.generic_analyst_agent import generic_analyst_agent
        from ai_agents.vectosports.reviewers.reviewer_agent_generic import reviewer_agent_generic
        
        from ai_agents.vectosports.coaches.coach_agent import CoachAgent
        
        coach_agent = CoachAgent()
        
        self.workflow = SequentialAgent(
            name='generic_analysis_workflow',
            description='A three-step workflow for non-swimming sports: 1. General Analysis, 2. Review and Reporting, 3. Coach Tips Generation.',
            sub_agents=[
                generic_analyst_agent.agent,
                reviewer_agent_generic.agent,
                coach_agent.agent
            ]
        )

    async def run(self, payload):
        logger.info(f"Generic analysis workflow received payload: {payload}")
        result = await self.workflow.run(payload)
        logger.info(f"Generic analysis workflow returned result: {result}")
        return result

generic_analysis_workflow = GenericAnalysisWorkflow()
