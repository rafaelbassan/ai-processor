"""Running analysis workflow - two-step workflow for running sports."""

import logging

logger = logging.getLogger(__name__)

class RunningAnalysisWorkflow:
    def __init__(self):
        from google.adk.agents.sequential_agent import SequentialAgent
        from ai_agents.vectosports.analysts.running_analyst_agent import running_analyst_agent
        from ai_agents.vectosports.reviewers.reviewer_agent_running import reviewer_agent_running
        
        from ai_agents.vectosports.coaches.coach_agent import CoachAgent
        
        coach_agent = CoachAgent()
        
        self.workflow = SequentialAgent(
            name='running_analysis_workflow',
            description='A three-step workflow for running: 1. Specialist Analysis, 2. Review and Reporting, 3. Coach Tips Generation.',
            sub_agents=[
                running_analyst_agent.agent,
                reviewer_agent_running.agent,
                coach_agent.agent
            ]
        )

    async def run(self, payload):
        logger.info(f"Running analysis workflow received payload: {payload}")
        result = await self.workflow.run(payload)
        logger.info(f"Running analysis workflow returned result: {result}")
        return result

running_analysis_workflow = RunningAnalysisWorkflow()
