import os
import re
import json
import httpx
import logging
from datetime import datetime
from pathlib import Path
from server.config import Config
from server.tools import TOOLS_SPEC, AVAILABLE_TOOLS
from db_server import db_manager

logger = logging.getLogger(__name__)

# Cache system prompt components
_soul_content = None
_memory_content = None

def get_soul_prompt():
    global _soul_content
    if _soul_content is None:
        soul_path = Path(__file__).resolve().parent / "SOUL.md"
        if soul_path.exists():
            with open(soul_path, "r", encoding="utf-8") as f:
                _soul_content = f.read()
        else:
            _soul_content = "You are Alex, receptionist for Radiant Smile Dental Clinic. Keep spoken sentences under 15 words. No markdown formatting."
    return _soul_content

def build_system_prompt(caller_phone: str = None):
    """
    Constructs the dynamic system prompt including SOUL, current date,
    and patient database context if available.
    """
    soul = get_soul_prompt()
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    
    # Check patient database
    patient_context = ""
    if caller_phone:
        patient = db_manager.get_patient(caller_phone)
        if patient:
            patient_context = (
                f"\n[Patient Profile Found]:\n"
                f"- Name: {patient['name']}\n"
                f"- Past History: {patient['history'] or 'None recorded'}\n"
                f"- Anxieties/Notes: {patient['anxieties'] or 'None recorded'}\n"
                f"Acknowledge the caller by name and make them feel comfortable."
            )
        else:
            patient_context = f"\n[Patient Profile]: New Caller (Number: {caller_phone}). Ask for their name when booking."
            
    system_prompt = (
        f"{soul}\n\n"
        f"--- CONTEXT ---\n"
        f"Current Date: {today_str}\n"
        f"{patient_context}\n\n"
        f"--- OPERATIONAL GUIDELINE ---\n"
        f"You must use the custom tools (clinic_info_retriever, calendar_appointment_booker) whenever "
        f"the caller asks for clinic logistics or scheduling. Do not hallucinate operational hours, pricing, "
        f"or availability. Retrieve facts first. Keep response short, professional, and friendly. plain text only!"
    )
    return system_prompt

class HermesAgent:
    def __init__(self, session_id: str, caller_phone: str = None):
        self.session_id = session_id
        self.caller_phone = caller_phone
        self.messages = [
            {"role": "system", "content": build_system_prompt(caller_phone)}
        ]
        
    async def process_message(self, user_text: str) -> str:
        """
        Sends the user statement to OpenRouter LLM, handles tool execution recursion,
        and returns the final verbal response string.
        """
        self.messages.append({"role": "user", "content": user_text})
        logger.info(f"Agent [Session {self.session_id}]: Processing user message. History size: {len(self.messages)}")
        
        headers = {
            "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/AnujanN/hermes-dental-assistant",
            "X-Title": "Radiant Smile Dental Assistant",
            "Content-Type": "application/json"
        }
        
        # Max recursive tool iterations
        max_iterations = 4
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for iteration in range(max_iterations):
                logger.debug(f"Agent [Session {self.session_id}]: Sending LLM request (iteration {iteration+1}/{max_iterations}). Model: {Config.OPENROUTER_MODEL}")
                payload = {
                    "model": Config.OPENROUTER_MODEL,
                    "messages": self.messages,
                    "tools": TOOLS_SPEC,
                    "tool_choice": "auto"
                }
                
                try:
                    response = await client.post(
                        f"{Config.OPENROUTER_BASE_URL}/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"OpenRouter API call failed. Status: {response.status_code}, Response: {response.text}")
                        return "I am having trouble connecting to my cognitive services. Please give me a moment."
                        
                    response_data = response.json()
                    choice = response_data["choices"][0]["message"]
                    
                    # Store LLM message in context
                    self.messages.append(choice)
                    
                    # Check if model wants to run a tool
                    if "tool_calls" in choice and choice["tool_calls"]:
                        logger.info(f"Agent [Session {self.session_id}]: LLM requested {len(choice['tool_calls'])} tool execution(s).")
                        for tool_call in choice["tool_calls"]:
                            tool_name = tool_call["function"]["name"]
                            tool_args = json.loads(tool_call["function"]["arguments"])
                            tool_id = tool_call["id"]
                            
                            logger.info(f"Agent [Session {self.session_id}] calls tool: '{tool_name}' with args: {tool_args}")
                            
                            # Execute local Python function
                            if tool_name in AVAILABLE_TOOLS:
                                # Inject phone number if booking tool doesn't resolve it or caller is known
                                if tool_name == "calendar_appointment_booker" and not tool_args.get("phone_number") and self.caller_phone:
                                    tool_args["phone_number"] = self.caller_phone
                                    
                                tool_result = AVAILABLE_TOOLS[tool_name](**tool_args)
                            else:
                                tool_result = f"Error: Tool '{tool_name}' not implemented."
                                
                            logger.info(f"Agent [Session {self.session_id}]: Tool '{tool_name}' returned: {tool_result}")
                            
                            # Append tool results back
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "name": tool_name,
                                "content": tool_result
                            })
                        # Continue loop to call LLM again with tool outputs
                        continue
                    else:
                        # No tool calls, return final spoken text
                        content = choice.get("content", "")
                        logger.debug(f"Agent [Session {self.session_id}]: Generated final response: '{content}'")
                        return self._clean_verbal_response(content)
                        
                except Exception as e:
                    logger.exception(f"Exception during LLM message processing in Session {self.session_id}: {e}")
                    return "Sorry, I encountered a connection error. Could you repeat that?"
                    
            return "I apologize, but I am processing too many operations right now. Can we try again?"

    def _clean_verbal_response(self, text: str) -> str:
        """Enforces SOUL rules: strip markdown and keep under 15 words if possible"""
        if not text:
            return ""
            
        # Strip markdown symbols
        clean = re.sub(r'[*_`#~\[\]\(\)]', '', text)
        clean = clean.replace("\n", " ").strip()
        
        # Split into words to assess count
        words = clean.split()
        if len(words) > 20: # soft limit check
            # We truncate and add emergency fallback or warning log
            # In production, we'd log a validation warning.
            pass
            
        return clean
