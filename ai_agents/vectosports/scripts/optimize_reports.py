
import os
import sys
import asyncio
import logging
from pathlib import Path
from google import genai
from google.genai import types

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OPTIMIZATION_INSTRUCTION = """You are a Senior Elite Biomechanics Specialist. 
Your task is to REWRITE an existing "Relatório de Evolução Biomecânica" to match new quality standards.

**GOAL:**
Transform the input report into a highly detailed, professional, and sophisticated document (multi-page depth).
The input report may be "stiff" or "templated". You must rewrite the narrative to be organic and personalized.

**CRITICAL RULES (Must Follow):**
1.  **TONE:** Maintain a **SOBER, SCIENTIFIC, and CAUTIOUS** tone. Remove any "hyped" language. Use precise biomechanical terms.
2.  **NO CLICHÉS:** REMOVE all stock phrases. Replace them with technical observations specific to this athlete.
3.  **MENTOR INTEGRATION:** Incorporate the presence and authority of the clínica's mentors (Guilherme Guido - Costas, João Gomes Junior - Peito, Murilo Sartori - Borboleta, Lorraine Ferreira - Crawl) within the narrative (e.g., in the Summary or Intro). Mention their competitive highlights:
    - **Guilherme Guido**: 3 olimpíadas e recordista mundial.
    - **João Gomes Junior**: Medalhista mundial/Pan e finalista olímpico.
    - **Murilo Sartori**: Finalista olímpico e medalhista mundial/Pan.
    - **Lorraine Ferreira**: Ouro Pan-Americano e 9 títulos brasileiros.
4.  **PEDAGOGICAL CONTEXT:** Infer and describe the athlete's motor learning stage (Cognitivo, Associativo ou Autônomo) based on the technical complexity of the report's observations. 
    - *Basic postural/alignment fixes* = Estágio Cognitivo.
    - *Refinements in stroke timing/efficiency* = Estágio Associativo.
    - *Micro-adjustments in propulsive vectors* = Estágio Autônomo.
5.  **PRESERVE HEADER:** Keep the exact title "Clínica Guilherme Guido - Análise Biomecânica Avançada" from the input. Do NOT add subtitles or alternative names.
5.  **TECHNICAL EXPANSION:** Break down the analysis into stroke phases (Entrada, Agarre, Puxada, Empurre, Recuperação/Finalização) provided in the input. **STRICT RULE:** Do not invent new errors. Instead, detail the *biomechanical consequences* of identified errors and the *mechanical rationale* of corrections.
6.  **DYNAMIC SCIENCE:** Use a "toolbox" of principles (Bernoulli/Sustentação, Arquimedes/Flutuabilidade, Newton/Ação-Reação, Mecânica de Alavancas, Teoria de Vórtices). Select the 2-3 most relevant principles for the athlete's specific errors.
7.  **STRUCTURE:** Ensure the final report follows this order exactly:
    - 1. RESUMO EXECUTIVO DETALHADO (With Pedagogical Stage & Level Context)
    - 2. ANÁLISE TÉCNICA APROFUNDADA (Per style, with Mentor citations)
    - 3. FUNDAMENTAÇÃO BIOMECÂNICA E CIENTÍFICA (Principles)
    - 4. ANÁLISE VISUAL E MARCADORES DE PERFORMANCE
    - 5. PLANO DE AÇÃO E RECOMENDAÇÕES
    - 6. PROJEÇÃO DE DESENVOLVIMENTO A LONGO PRAZO
    - 7. OBSERVAÇÕES PARA O TREINADOR/RESPONSÁVEL
    - 8. CONSIDERAÇÕES FINAIS
    - 9. GLOSSÁRIO TÉCNICO
    - REFERÊNCIAS BIBLIOGRÁFICAS

7.  **NO TIMESTAMPS:** REMOVE all timestamp mentions (e.g., "[00:15]", "minuto 1:20", "aos 10 segundos"). They are not useful in the final printed report.
8.  **NO MATH FORMULAS:** Use text descriptions only.

9.  **REALISTIC CONTEXT (CRITICAL):**
    - Contextualize that the analysis uses high-performance biomechanics as a **reference model** for learning, but acknowledge the athlete is in a **developmental phase**.
    - **AVOID EXAGGERATION:** Do NOT say the athlete "reached international elite level" or "elevated to olympic efficiency".
    - Instead, use phrases like: "Improving fundamentals", "Building a solid technical base", "Developing correct motor patterns".
    - **TONE:** Be encouraging but **GROUNDED**. Remember these are often children/juniors.
    - **IMPORTANT:** DO NOT include columns for "Referência Técnica" or "Especialista Responsável" in the header table. Keep the table simple: Atleta, Data e Referência. Only the header title "Clínica Guilherme Guido" is allowed.

10. **MENTOR INTEGRATION:** Frame the analysis as being guided by the clinic's specialized mentors for each style.
    - **Costas (Backstroke):** Mention **Guilherme Guido** as the style mentor (e.g., "Seguindo os fundamentos ensinados por Guilherme Guido...").
    - **Peito (Breaststroke):** Mention **João Gomes Junior** as the style mentor.
    - **Borboleta (Butterfly):** Mention **Murilo Sartori** as the style mentor.
    - **Crawl (Freestyle):** Mention **Lorraine Ferreira** as the style mentor.
    - *Do not* list them in the intro; integrate their mentorship authority deeply into the technical feedback.
**INPUT:** Existing markdown report.
**OUTPUT:** Fully expanded and rewritten markdown report (pt-BR).
"""

async def optimize_file(client: genai.Client, file_path: Path):
    logger.info(f"Processing {file_path}...")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        response = client.models.generate_content(
            model='gemini-3-flash-preview', # fast and good enough for rewriting, or use pro
            config=types.GenerateContentConfig(
                temperature=0.5, # As requested for variability
                system_instruction=OPTIMIZATION_INSTRUCTION
            ),
            contents=[content]
        )
        
        optimized_content = response.text
        
        # Extract content if wrapped in tags (optional, but good practice if model adds them)
        import re
        match = re.search(r'<!--FINAL_REPORT_STRUCTURE_START-->(.*?)<!--FINAL_REPORT_STRUCTURE_END-->', optimized_content, re.DOTALL)
        if match:
            optimized_content = match.group(1).strip()
            # Re-add tags for consistency
            optimized_content = f"<!--FINAL_REPORT_STRUCTURE_START-->\n{optimized_content}\n<!--FINAL_REPORT_STRUCTURE_END-->"
            
        # Overwrite or save as new? Let's save as _optimized.md for safety first
        new_path = file_path.parent / f"{file_path.stem}_optimized.md"
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(optimized_content)
            
        logger.info(f"✅ Saved optimized report to {new_path}")
        
    except Exception as e:
        logger.error(f"❌ Failed to optimize {file_path}: {e}")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python optimize_reports.py <directory_path>")
        sys.exit(1)
        
    target_dir = Path(sys.argv[1])
    if not target_dir.exists():
        print(f"Directory {target_dir} not found.")
        sys.exit(1)

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY environment variable not set.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    tasks = []
    # Recursively find .md files
    for md_file in target_dir.glob("**/*.md"):
        if "_optimized.md" in md_file.name:
            continue # Skip already optimized files
        tasks.append(optimize_file(client, md_file))
        
    if not tasks:
        logger.info("No markdown files found to process.")
        return

    logger.info(f"Found {len(tasks)} reports to optimize.")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
