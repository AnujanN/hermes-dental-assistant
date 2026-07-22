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
    """Load and cache the SOUL.md persona file, falling back to a default."""
    global _soul_content
    if _soul_content is None:
        soul_path = Path(__file__).resolve().parent / "SOUL.md"
        try:
            if soul_path.exists():
                with open(soul_path, "r", encoding="utf-8") as f:
                    _soul_content = f.read()
                logger.debug("Loaded SOUL prompt from %s", soul_path)
            else:
                _soul_content = "You are Alex, receptionist for Radiant Smile Dental Clinic. Keep spoken sentences under 15 words. No markdown formatting."
                logger.warning("SOUL.md not found at %s; using default persona.", soul_path)
        except OSError as exc:
            logger.error("Failed to read SOUL.md at %s: %s", soul_path, exc, exc_info=True)
            _soul_content = "You are Alex, receptionist for Radiant Smile Dental Clinic. Keep spoken sentences under 15 words. No markdown formatting."
    return _soul_content


def _fetch_patient_context(caller_phone: str) -> str:
    """
    Query the patient database for *caller_phone* and return a context
    string for the system prompt.  Returns an empty string on failure so
    that the agent can still function when the DB is unavailable.
    """
    if not caller_phone:
        return ""

    try:
        patient = db_manager.get_patient(caller_phone)
        if patient:
            return (
                f"\n[Patient Profile Found]:\n"
                f"- Name: {patient['name']}\n"
                f"- Past History: {patient['history'] or 'None recorded'}\n"
                f"- Anxieties/Notes: {patient['anxieties'] or 'None recorded'}\n"
                f"Acknowledge the caller by name and make them feel comfortable."
            )
        else:
            return f"\n[Patient Profile]: New Caller (Number: {caller_phone}). Ask for their name when booking."
    except Exception as exc:
        logger.error(
            "Failed to fetch patient context for %s (agent will proceed without it): %s",
            caller_phone, exc, exc_info=True,
        )
        return ""


def build_system_prompt(caller_phone: str = None):
    """
    Constructs the dynamic system prompt including SOUL, current date,
    and patient database context if available.
    """
    soul = get_soul_prompt()
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    
    patient_context = _fetch_patient_context(caller_phone)
            
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


def _validate_session_id(session_id: str) -> str:
    """Validate that *session_id* is a non-empty string."""
    if not session_id or not str(session_id).strip():
        raise ValueError("session_id is required and cannot be empty.")
    return str(session_id).strip()


def _validate_user_input(text: str) -> str:
    """Validate that user input text is non-empty after stripping whitespace."""
    if not text or not text.strip():
        raise ValueError("User input text cannot be empty.")
    return text.strip()


class HermesAgent:
    def __init__(self, session_id: str, caller_phone: str = None):
        self.session_id = _validate_session_id(session_id)
        self.caller_phone = caller_phone
        self.messages = [
            {"role": "system", "content": build_system_prompt(caller_phone)}
        ]
        
    async def process_message(self, user_text: str) -> str:
        """
        Sends the user statement to OpenRouter LLM, handles tool execution recursion,
        and returns the final verbal response string.
        """
        try:
            user_text = _validate_user_input(user_text)
        except ValueError as exc:
            logger.warning("Agent [Session %s]: Rejected empty user input: %s", self.session_id, exc)
            return "I didn't catch that. Could you please repeat?"

        self.messages.append({"role": "user", "content": user_text})
        logger.info("Agent [Session %s]: Processing user message. History size: %d", self.session_id, len(self.messages))
        
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
                logger.debug(
                    "Agent [Session %s]: Sending LLM request (iteration %d/%d). Model: %s",
                    self.session_id, iteration + 1, max_iterations, Config.OPENROUTER_MODEL,
                )
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
                        logger.error(
                            "OpenRouter API call failed. Status: %d, Response: %s",
                            response.status_code, response.text,
                        )
                        return "I am having trouble connecting to my cognitive services. Please give me a moment."
                        
                    response_data = response.json()
                    choice = response_data["choices"][0]["message"]
                    
                    # Store LLM message in context
                    self.messages.append(choice)
                    
                    # Check if model wants to run a tool
                    if "tool_calls" in choice and choice["tool_calls"]:
                        logger.info(
                            "Agent [Session %s]: LLM requested %d tool execution(s).",
                            self.session_id, len(choice["tool_calls"]),
                        )
                        for tool_call in choice["tool_calls"]:
                            await self._execute_tool_call(tool_call)
                        # Continue loop to call LLM again with tool outputs
                        continue
                    else:
                        # No tool calls, return final spoken text
                        content = choice.get("content", "")
                        logger.debug("Agent [Session %s]: Generated final response: '%s'", self.session_id, content)
                        return self._clean_verbal_response(content)
                        
                except Exception as exc:
                    logger.exception(
                        "Exception during LLM message processing in Session %s: %s",
                        self.session_id, exc,
                    )
                    return "Sorry, I encountered a connection error. Could you repeat that?"
                    
            return "I apologize, but I am processing too many operations right now. Can we try again?"

    async def _execute_tool_call(self, tool_call: dict) -> None:
        """
        Execute a single LLM-requested tool call and append the result
        to the conversation history.
        """
        tool_name = tool_call["function"]["name"]
        tool_id = tool_call["id"]

        try:
            tool_args = json.loads(tool_call["function"]["arguments"])
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error(
                "Agent [Session %s]: Failed to parse arguments for tool '%s': %s",
                self.session_id, tool_name, exc,
            )
            self.messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "name": tool_name,
                "content": f"Error: Could not parse tool arguments — {exc}",
            })
            return

        logger.info("Agent [Session %s] calls tool: '%s' with args: %s", self.session_id, tool_name, tool_args)

        if tool_name in AVAILABLE_TOOLS:
            try:
                # Inject phone number if booking tool doesn't resolve it or caller is known
                if tool_name == "calendar_appointment_booker" and not tool_args.get("phone_number") and self.caller_phone:
                    tool_args["phone_number"] = self.caller_phone

                tool_result = AVAILABLE_TOOLS[tool_name](**tool_args)
            except Exception as exc:
                logger.error(
                    "Agent [Session %s]: Tool '%s' raised an exception: %s",
                    self.session_id, tool_name, exc, exc_info=True,
                )
                tool_result = f"Error executing tool '{tool_name}': {exc}"
        else:
            logger.warning("Agent [Session %s]: Tool '%s' is not implemented.", self.session_id, tool_name)
            tool_result = f"Error: Tool '{tool_name}' not implemented."

        logger.info("Agent [Session %s]: Tool '%s' returned: %s", self.session_id, tool_name, tool_result)

        # Append tool results back
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_id,
            "name": tool_name,
            "content": tool_result
        })

    def _clean_verbal_response(self, text: str) -> str:
        """Enforces SOUL rules: strip markdown and keep under 15 words if possible"""
        if not text:
            return ""
        
        try:
            # Strip markdown symbols
            clean = re.sub(r'[*_`#~\[\]\(\)]', '', text)
            clean = clean.replace("\n", " ").strip()
            
            # Split into words to assess count
            words = clean.split()
            if len(words) > 15:
                clean = " ".join(words[:15]).rstrip(" ,;:-") + "."
                
            return clean
        except Exception as exc:
            logger.error("Failed to clean verbal response: %s", exc, exc_info=True)
            return text
