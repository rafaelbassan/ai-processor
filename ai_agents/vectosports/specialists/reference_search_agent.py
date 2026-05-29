"""Reference Search Agent - searches for biomechanical standards and drills."""

import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class ReferenceSearchAgent:
    def __init__(self):
        from google.adk.agents.llm_agent import Agent
        from google.genai import types
        
        self.agent = Agent(
            model='gemini-3-flash-preview',
            generate_content_config=types.GenerateContentConfig(
                temperature=0.0
            ),
            name='reference_search_agent',
            description='Searches for biomechanical standards, common errors, and correction drills for specific sports and styles.',
            instruction="""You are a Reference Search Specialist.

Your task is to find reliable biomechanical standards, common errors, and correction drills for a specific sport and style (e.g., Swimming - Crawl/Freestyle).

You will receive a query containing the Sport, Style, and specific areas of focus (e.g., "High Elbow Catch", "Streamline").

Your output should be a structured summary including:
1. **Biomechanical Standards**: What is considered the "ideal" technique? (Cite sources if possible).
2. **Common Errors**: What are the typical mistakes athletes make in this area?
3. **Correction Drills**: List specific drills to fix these errors.

Use your web search tool to find this information. Prioritize authoritative sources like swim swam, biomechanics journals, or expert coaching sites.

Format your response in Markdown.
""",
            sub_agents=[]
        )

    async def run(self, payload: str):
        """
        Executes the agent using the ADK Runner.
        """
        logger.info(f"Reference search agent received payload: {payload}")
        
        # Imports needed for Runner execution
        from google.adk.sessions import InMemorySessionService
        from google.adk.runners import Runner
        from google.genai.types import Part, Content
        
        # Prepare content
        user_content = Content(role="user", parts=[Part(text=str(payload))])
        
        # Setup session (stateless for this simple agent, so we create a new one each time)
        session_service = InMemorySessionService()
        import uuid
        session_id = f"ref-search-{uuid.uuid4()}"
        user_id = "system-process"
        
        runner = Runner(
            app_name="vectosports_reference_search",
            agent=self.agent,
            session_service=session_service
        )
        
        # Create session
        try:
             # Ensure we have an event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            await session_service.create_session(
                user_id=user_id,
                session_id=session_id,
                app_name="vectosports_reference_search"
            )
            
            # Run
            events = []
            for event in runner.run(
                user_id=user_id,
                session_id=session_id,
                new_message=user_content
            ):
                events.append(event)
            
            # Extract Text
            response_text = ""
            for event in events:
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts'):
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                response_text += part.text
                    elif hasattr(event.content, 'text'):
                         response_text += event.content.text
                elif hasattr(event, 'text') and event.text:
                    response_text += event.text
            
            logger.info(f"Reference search agent returned result length: {len(response_text)}")
            return response_text
            
        except Exception as e:
            logger.error(f"Error running ReferenceSearchAgent: {e}")
            # Fallback or re-raise
            raise

reference_search_agent = ReferenceSearchAgent()
