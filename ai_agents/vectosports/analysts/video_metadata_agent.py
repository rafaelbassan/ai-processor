"""Video Metadata Agent - extracts sport and camera angle from video, then routes to appropriate workflow."""

import logging
import os

logger = logging.getLogger(__name__)

class VideoMetadataAgent:
    def __init__(self):
        logger.info("    - Importing Agent and types...")
        from google.adk.agents.llm_agent import Agent
        from google.genai import types
        logger.info("    - Importing swimming_analysis_workflow...")
        from ai_agents.vectosports.workflows.swimming_analysis_workflow import swimming_analysis_workflow
        logger.info("    - Importing running_analysis_workflow...")
        from ai_agents.vectosports.workflows.running_analysis_workflow import running_analysis_workflow
        logger.info("    - Importing generic_analysis_workflow...")
        from ai_agents.vectosports.workflows.generic_analysis_workflow import generic_analysis_workflow
        logger.info("    - Workflows imported")
        
        # Configure API key for Google AI
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        
        self.agent = Agent(
            model='gemini-3-flash-preview',
            generate_content_config=types.GenerateContentConfig(
                temperature=0.0
            ),
            name='video_metadata_agent',
            description='Specialist agent that analyzes video content to identify the sport and camera angle/view, then routes to the appropriate analysis workflow.',
            instruction="""You are a video analysis specialist responsible for identifying the sport and routing to the correct analysis workflow.

**Your task has THREE steps:**

**Step 1: Analyze the context and video to identify Metadata:**
1. The Sport being performed.
2. The Camera Angle or View (e.g., side view, front view, underwater side view, overhead view).
3. **For Swimming specifically:** Identify the stroke type (crawl/freestyle, backstroke, breaststroke, butterfly) and the phase of the swim (start, turn, finish, or main swimming).

**CRITICAL for Stroke Identification:** 
- **Check the Filename:** The user often includes the stroke name in the file path (e.g., "peito" for breaststroke, "costas" to backstroke, "borboleta" for butterfly, "crawl" or "livre" for freestyle). If the filename suggests a stroke, trust it unless visual evidence clearly contradicts it.
- **Check Instructions:** If the coach or user mentions a specific stroke in the "Instructions", prioritize this information above all else.
- **Visual Evidence:** Use the visual clues below to confirm or identify the stroke if not explicitly stated in context.

**Step 2: Perform a Detailed Pre-Analysis (extract maximum information):**
Observe and describe in detail:
- **Environment:** Pool/track type, lane markers, lighting conditions, water clarity.
- **Athlete:** Attire (suit color, cap color), visible equipment (fins, paddles, snorkel), approximate age group/level if discernible.
- **Movement Quality:** General impression of technique, rhythm, body position, obvious major errors or excellent features.
- **Video Quality:** Stability, framing, resolution issues, underwater/above water transitions.
- **Key Events:** Start, turn, finish, specific drills being performed.

Compile this information into a "pre_analysis" summary.

**Step 3: Route to the appropriate workflow based on the sport:**
- If the sport is Swimming → transfer to `swimming_analysis_workflow` with identified stroke, phase, AND the `pre_analysis` data.
- If the sport is Running (Corrida) → transfer to `running_analysis_workflow` with `pre_analysis` data.
- For any other sport → transfer to `generic_analysis_workflow` with `pre_analysis` data.

**IMPORTANT:** After identifying the sport and performing the pre-analysis, you MUST transfer to the appropriate workflow. Include all the original request information (athlete data, instructions, etc.) plus the identified metadata and pre-analysis when transferring.

**Visual Clues for Swimming:**
   - **Stroke identification:**
     - Crawl/Freestyle: Alternating arm movements.
       * **Head/Face:** Nape faces surface. Face looks at bottom, visible only during breathing rotation.
       * **Kick Mechanics:** Power phase is DOWNWARD. Foot kicks towards bottom. Ankle extension pushes water back and down.
       * **Arm Stroke:** Hand entry in front of head, pull phase under body towards thigh.
       * **Alignment:** Spine forms straight line with nape. Expiration bubbles go down before up.
     - Backstroke (Costas): Swimmer on back, arms alternating over shoulders.
       * **CRITICAL DISTINCTION vs CRAWL:**
       * **Head/Face:** Face is UP, water breaks on the FOREHEAD. (In crawl, we see back of cap).
       * **Kick Mechanics:** Propulsion is UPWARD (towards surface). Knee flexion prepares for an UPWARD kick. (In crawl, force is downward).
       * **Surface:** Knees come close to surface creating small UPWARD ripples/bubbles.
       * **Trunk:** Chest faces surface. Tracking lines show dorsal inclination.
     - Breaststroke: Simultaneous arm and leg movements.
       * **Symmetry:** Left side mirrors right side perfectly.
       * **Kick Mechanics (Frog Kick):** Knees flex and separate laterally, feet whip circular out and back ("heart" shape trajectory).
       * **Glide Phase:** Distinct pause where swimmer is fully extended and motionless (streamline).
       * **Vertical Movement:** Trunk undulates vertically for frontal breathing, then dives chest.
     - Butterfly: Simultaneous arm movements, dolphin kick.
       * **Dolphin Kick:** Legs act as single fin (no alternation). Movement flows from hips to feet.
       * **Arm Recovery:** Both arms exit/enter water simultaneously.
       * **Undulation:** Body "snakes" (sinusoidal movement). Chest sinks as hips rise.
       * **Rhythm:** Two kicks per arm cycle (entry and exit).
   - **Phase identification:**
     - Start: Diver entering water, initial push-off
     - Turn: Swimmer approaching wall, flip turn or touch turn
     - Finish: Final strokes towards wall, touch finish
     - Main swimming: Continuous swimming in the middle of the pool
   - Consider overall body position, arm depth (backstroke has shallower pulls), head orientation (backstroke head not looking down), leg movements, and any visible patterns throughout the video.

Example flow:
1. Observe: "The video shows a swimmer performing backstroke from a side perspective, with shallow arm pulls and head facing up"
2. Identify: Sport = Swimming, Stroke = Backstroke, Phase = Main swimming, Camera Angle = Side View
3. Pre-Analysis: "Pool is indoor, well lit. Swimmer wears black suit, white cap. Technique looks smooth but hips are low. Video is stable."
4. Action: Transfer to swimming_analysis_workflow with the full context including stroke, phase, and pre_analysis details
""",
            sub_agents=[
                swimming_analysis_workflow.workflow,
                running_analysis_workflow.workflow,
                generic_analysis_workflow.workflow
            ]
        )

video_metadata_agent = VideoMetadataAgent()
