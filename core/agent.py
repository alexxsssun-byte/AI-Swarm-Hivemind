from google import genai
from google.genai import types
import os
import concurrent.futures
from .memory import get_conversation_history, add_message, get_assumptions

PERSONAS = {
    "The Bull": """You are The Bull, a Growth Specialist AI Investment Banker. 
Always look for the upside, massive synergistic value, aggressive revenue growth, and high exit multiples. 
Be enthusiastic and aggressive. If The Bear or The Quant raised points previously, explicitly attack their assumptions and aggressively defend your growth thesis.
KEEP IT CONCISE (1-2 short paragraphs).
""",
    "The Bear": """You are The Bear, a Risk Manager AI Investment Banker. 
Always find flaws, highlight macroeconomic risks, margin compression, debt service issues, and integration risks. 
Be highly skeptical. You MUST directly attack the arguments made by The Bull. Expose the downside and why their growth plan will fail.
KEEP IT CONCISE (1-2 short paragraphs).
""",
    "The Quant": """You are The Quant, an AI Investment Banking expert in structuring and modeling. 
Focus strictly on the numbers, WACC, debt capacity, valuation methodologies, and covenants. 
Look at the aggressive arguments of The Bull and the fears of The Bear, and provide grounded mathematical reality. Call out whoever is mathematically wrong.
If a financial model or slide deck is asked for or seems highly relevant, mention you will use your tools to generate it.
KEEP IT CONCISE (1-2 short paragraphs).
""",
    "The MD": """You are The Managing Director (The MD) of this AI Investment Banking team. 
You listen to the debate between The Bull, The Bear, and The Quant.
DO NOT reach a consensus early. If The Bear or The Quant raise valid concerns, or if The Bull's assumptions are unchecked, you MUST ask a hard follow-up question and let them continue arguing.
Only achieve consensus if the team is completely aligned.
IMPORTANT: If you are finally ready to conclude the debate and advise the client, you MUST begin your response exactly with the phrase "CONSENSUS REACHED:" followed by your conclusion.
If you feel the team needs to debate an unresolved point further before a decision can be made, ask them a guiding question and DO NOT use that phrase.
"""
}

class TradingFloor:
    def __init__(self, project_name: str, project_id: int):
        self.project_name = project_name
        self.project_id = project_id
        
        self.client = genai.Client()
        self.model_name = "gemini-2.5-flash"
        self.tools = []

    def _determine_personas(self, user_message: str):
        prompt = f"""Based on the following user message, generate a team of 3 to 4 hyper-specialized AI personas best suited to analyze, debate, and solve the problem.
If the question is about marketing, generate demographics or market analysts. If it's about tech, software engineers/architects, etc.
End the team with a moderator/leader who can guide the discussion and reach a consensus.

User Message: {user_message}

Return a JSON array of objects directly (no markdown formatting, no JSON blocks, just the raw array). Each object must have:
- "name": A concise, distinct name (e.g., The Tech Lead, Gen-Z Consumer)
- "system_prompt": A 1-2 paragraph description of their role, perspective, and what they should focus on. Mention they must be concise and state they should argue their specific viewpoint. The final moderator's prompt should instruct them to conclude with 'CONSENSUS REACHED:' when appropriate.
- "avatar": A single relevant emoji for this persona.
- "color": A hex color code (e.g., #3b82f6) for their node in a graph. Ensure colors are readable and distinct."""
        
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7
                )
            )
            import json
            personas_list = json.loads(resp.text)
            
            # Reformat to match the structure we need
            dynamic_personas = {}
            for p in personas_list:
                dynamic_personas[p["name"]] = {
                    "system_prompt": p.get("system_prompt", f"You are {p['name']}. Provide your perspective."),
                    "avatar": p.get("avatar", "🤖"),
                    "color": p.get("color", "#888888")
                }
            return dynamic_personas
        except Exception as e:
            print(f"Error generating dynamic personas: {e}. Falling back to default.")
            return None

    def set_tools(self, tool_funcs):
        self.tools = tool_funcs

    def _format_history_for_persona(self, history, current_assumptions):
        formatted_history = []
        for msg in history:
            role = "user" if msg['role'] == "user" else "model"
            content = msg['content']
            # If it's a model message but belongs to a specific persona, prepend their name so context is clear to Gemini
            if role == "model" and msg['role'] not in ["user", "model"]:
                content = f"[{msg['role']} said]: {content}"
            formatted_history.append(types.Content(role=role, parts=[types.Part.from_text(text=content)]))
            
        context_msg = f"\n[SYSTEM CONTEXT: Current Project Assumptions: {current_assumptions}]"
        
        if formatted_history and formatted_history[-1].role == 'user':
            formatted_history[-1].parts[0].text += context_msg
            
        return formatted_history

    def _squash_history(self, history):
        if not history:
            return []
        squashed = []
        current_role = history[0].role
        current_parts = list(history[0].parts)
        
        for msg in history[1:]:
            if msg.role == current_role:
                # Add a separator between squashed messages
                current_parts.append(types.Part.from_text(text="\n\n---\n\n"))
                current_parts.extend(msg.parts)
            else:
                squashed.append(types.Content(role=current_role, parts=current_parts))
                current_role = msg.role
                current_parts = list(msg.parts)
        squashed.append(types.Content(role=current_role, parts=current_parts))
        
        # Ensure it doesn't end with a model message if we are about to generate
        # Actually it's fine for generate_content to end with a user message.
        # But if it ends with a model message, and we are going to generate another model message?
        # Actually generate_content always expects to predict the NEXT message. So history should end with `user`.
        # If the squashed history ends with `model`, we append a dummy user prompt "Please continue the discussion."
        if squashed and squashed[-1].role == "model":
            squashed.append(types.Content(role="user", parts=[types.Part.from_text(text="Please respond to the above.")]))
            
        return squashed

    def _generate_with_tools(self, squashed_history, config, tools):
        resp = self.client.models.generate_content(
            model=self.model_name,
            contents=squashed_history,
            config=config
        )
        
        tool_call_count = 0
        while resp.function_calls and tool_call_count < 3:
            tool_call_count += 1
            squashed_history.append(resp.candidates[0].content)
            
            parts = []
            for fc in resp.function_calls:
                func = next((t for t in (tools or []) if t.__name__ == fc.name), None)
                if func:
                    try:
                        result = func(**fc.args)
                        if not isinstance(result, dict):
                            result = {"result": result}
                    except Exception as e:
                        result = {"error": str(e)}
                else:
                    result = {"error": f"Tool {fc.name} not found."}
                
                parts.append(types.Part.from_function_response(name=fc.name, response=result))
                
            squashed_history.append(types.Content(role="user", parts=parts))
            
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=squashed_history,
                config=config
            )
            
        return resp

    def chat(self, user_message: str, swarm_mode: str = "Banking Team (Default)"):
        add_message(self.project_id, "user", user_message)
        
        # Get history (limit to last 30 for context window so we have room for all agents)
        history = get_conversation_history(self.project_id, limit=30)
        assumptions = get_assumptions(self.project_id)
        
        base_history = self._format_history_for_persona(history, assumptions)
        
        meeting_order = ["The Bull", "The Bear", "The Quant", "The MD"]
        active_personas = {k: {"system_prompt": v, "avatar": None, "color": None} for k, v in PERSONAS.items()}
        
        if swarm_mode == "Dynamic Personas (Auto-generated)":
            dynamic = self._determine_personas(user_message)
            if dynamic and len(dynamic) > 0:
                meeting_order = list(dynamic.keys())
                active_personas = dynamic
                
        def run_agent_turn(persona, history_copy, sys_prompt, temp, tools):
            config = types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=temp, 
                tools=tools
            )
            squashed = self._squash_history(history_copy)
            resp = self._generate_with_tools(squashed, config, tools)
            try:
                final_text = resp.text
            except ValueError:
                final_text = ""
            if not final_text:
                final_text = "Agreed."
            if resp.function_calls:
                final_text += f"\n\n[Agent invoked tools: {', '.join([fc.name for fc in resp.function_calls])}]"
            return persona, final_text
        
        # PHASE 1: Independent Initial Reads
        phase1_responses = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(meeting_order)) as executor:
            futures = []
            for persona in meeting_order:
                sys_prompt = active_personas[persona]["system_prompt"] + "\n\n(PHASE 1: State your initial independent thoughts on the task.)"
                temp = 0.3 if persona != "The Quant" else 0.1
                tools = self.tools if self.tools else None
                futures.append(executor.submit(run_agent_turn, persona, list(base_history), sys_prompt, temp, tools))
                
            for future in concurrent.futures.as_completed(futures):
                persona, final_text = future.result()
                phase1_responses[persona] = final_text
                node_id = f"{persona}_1"
                
                yield {
                    "agent": persona, 
                    "text": final_text,
                    "sources": ["user"],
                    "round": 1,
                    "node_id": node_id,
                    "avatar": active_personas[persona].get("avatar"),
                    "color": active_personas[persona].get("color")
                }
                add_message(self.project_id, persona, final_text)
            
        # Compile Phase 1 history to feed into Phase 2
        current_history = list(base_history)
        phase1_text = "ROOM INITIAL OPINIONS:\n"
        for p in meeting_order: # Must append consistently despite async completion
            if p in phase1_responses:
                phase1_text += f"\n[{p} stated]: {phase1_responses[p]}\n"
            
        current_history.append(types.Content(role="user", parts=[types.Part.from_text(text=phase1_text)]))

        # PHASE 2: Open Debate Loop
        max_rounds = 10
        for round_idx in range(2, max_rounds + 1):
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(meeting_order)) as executor:
                round_responses = {}
                futures = []
                for persona in meeting_order:
                    sys_prompt = active_personas[persona]["system_prompt"] + "\n\n(PHASE 2: You are in an open room debate. Read what everyone else just said and directly attack their flaws or reinforce your stance.)"
                    temp = 0.4 if persona != "The Quant" else 0.1
                    tools = self.tools if self.tools else None
                    futures.append(executor.submit(run_agent_turn, persona, list(current_history), sys_prompt, temp, tools))
                    
                consensus_reached = False
                for future in concurrent.futures.as_completed(futures):
                    persona, final_text = future.result()
                    round_responses[persona] = final_text
                    
                    # Compute sources dynamically
                    sources = [f"{p}_{round_idx-1}" for p in meeting_order if p != persona]
                    
                    yield {
                        "agent": persona, 
                        "text": final_text,
                        "sources": sources,
                        "round": round_idx,
                        "node_id": f"{persona}_{round_idx}",
                        "avatar": active_personas[persona].get("avatar"),
                        "color": active_personas[persona].get("color")
                    }
                    add_message(self.project_id, persona, final_text)
                    
                    if persona == "The MD" or persona == meeting_order[-1]:
                        if "CONSENSUS REACHED:" in final_text.upper():
                            consensus_reached = True
                            break
                            
                # Update current_history with all responses from this round
                for p in meeting_order:
                    if p in round_responses:
                        current_history.append(types.Content(role="user", parts=[types.Part.from_text(text=f"[{p} added]:\n{round_responses[p]}")]))
                
                if consensus_reached:
                    return

