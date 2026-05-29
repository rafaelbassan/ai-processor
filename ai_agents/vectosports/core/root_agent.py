"""Root agent - main dispatcher for the athlete analysis system."""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class RootAgent:
    def __init__(self):
        logger.info("  - Importing Agent...")
        from google.adk.agents.llm_agent import Agent
        logger.info("  - Importing performance_analyst_agent...")
        from ai_agents.vectosports.specialists.performance_analyst_agent import performance_analyst_agent
        logger.info("  - Importing nutritionist_agent...")
        from ai_agents.vectosports.specialists.nutritionist_agent import nutritionist_agent
        logger.info("  - Importing video_metadata_agent...")
        from ai_agents.vectosports.analysts.video_metadata_agent import video_metadata_agent
        logger.info("  - Sub-agents imported")
        
        # Configure API key for Google AI
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        
        self.agent = Agent(
            model='gemini-3-flash-preview',
            name='root_agent',
            description='Main coordinator for athlete biomechanical analysis. Routes requests to sport-specific analysis workflows.',
            instruction="""You are the coordinator for an athlete biomechanical analysis system.

Your role is to route requests to the appropriate specialist based on the user's needs.

**Routing Rules:**

1. **Biomechanical Analysis (Technique, Movement, Video Analysis):**
   - ALWAYS transfer these requests to the `video_metadata_agent`.
   - The `video_metadata_agent` will verify if the sport and camera angle are known, analyze the video if necessary, and then route to the specific sport workflow (Swimming or Generic).

2. **Performance & Competition Analysis:**
   - Transfer to `performance_analyst_agent`.

3. **Nutritional Advice:**
   - Transfer to `nutritionist_agent`.

The user will provide:
- Athlete information (name, ID)
- Video and image files for analysis
- Specific instructions or coach notes

Simply identify the type of request and transfer to the appropriate agent using the available tools.
Do not attempt to analyze the videos yourself.

Always respond in the language specified in the user message (e.g., 'Language: pt-br' for Portuguese). If not specified, default to English.""",
            sub_agents=[
                performance_analyst_agent.agent,
                nutritionist_agent.agent,
                video_metadata_agent.agent
            ]
        )

    def run(self, user_id, session_id, new_message):
        """
        Run the root agent using the Google ADK Runner.
        This is the correct way to use the ADK agents with session management.
        
        Args:
            user_id: User identifier for the session
            session_id: Session identifier
            new_message: Message to send (str or Content object)
        
        Returns:
            str: Analysis result text
        """
        from google.adk.sessions import InMemorySessionService
        from google.adk.runners import Runner
        from google.genai.types import Part, Content
        import asyncio
        
        # Add current time to the message context
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(new_message, str):
            new_message = f"{new_message}\n\n[System Context: Current Date/Time: {current_time}]"

        logger.info(f"Root Agent received input:")
        logger.info(f"  User ID: {user_id}")
        logger.info(f"  Session ID: {session_id}")
        logger.info(f"  Message type: {type(new_message)}")
        
        # Prepare the message in the correct format
        if isinstance(new_message, str):
            user_content = Content(role="user", parts=[Part(text=new_message)])
        elif hasattr(new_message, 'parts'):
            # Already a Content object
            user_content = new_message
        else:
            user_content = Content(role="user", parts=[Part(text=str(new_message))])
        
        # Initialize session service and runner
        logger.info("Initializing session service and runner...")
        session_service = InMemorySessionService()
        runner = Runner(
            app_name="vectosports_analysis",
            agent=self.agent,
            session_service=session_service
        )
        
        # Create session
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(session_service.create_session(
            user_id=user_id,
            session_id=session_id,
            app_name="vectosports_analysis"
        ))
        logger.info(f"Session created: {session_id}")
        
        # Run AI analysis
        logger.info("Running AI analysis via Runner...")
        events = []
        
        for event in runner.run(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content
        ):
            events.append(event)
            logger.info(f"Event: {type(event).__name__}")
        
        logger.info(f"Analysis completed. Total events: {len(events)}")
        
        # Extract results - only text content
        analysis_parts = []
        for event in events:
            # Try to get content from various attributes
            if hasattr(event, 'content') and event.content:
                # Handle Content object - extract parts
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        # Only extract text parts, skip function calls and other non-text parts
                        if hasattr(part, 'text') and part.text:
                            analysis_parts.append(str(part.text))
                        # Skip non-text parts (function_call, file_data, etc.)
                else:
                    # Try to get text from the content object itself
                    if hasattr(event.content, 'text') and event.content.text:
                        analysis_parts.append(str(event.content.text))
            elif hasattr(event, 'text') and event.text:
                analysis_parts.append(str(event.text))
            elif hasattr(event, 'message') and event.message:
                # Only add message if it's a string, not an object
                if isinstance(event.message, str):
                    analysis_parts.append(event.message)
        
        result = "\n".join(analysis_parts)
        logger.info(f"Final result length: {len(result)} chars")
        
        return result


root_agent = RootAgent()
