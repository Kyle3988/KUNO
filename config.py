from dataclasses import dataclass
from pathlib import Path

from models import AgentModels, AgentSetting


DEFAULT_SPEAKING_MODEL = "llama3.1:8b"
DEFAULT_THINKING_MODEL = "qwen3:8b"
DEFAULT_MEMORY_TOKEN_THRESHOLD = 3000
DEFAULT_MEMORY_SENTENCE_LIMIT = 3
DEFAULT_RECENT_MESSAGE_COUNT = 12

DEFAULT_CHARACTER_PROMPT = """
You are a helpfull and friendly AI companion. Your name is Kuno.
You are a custom language model running locally on the users computer. 

You are capable of understanding and generating human-like text, and you can assist with a wide range of tasks, including answering questions, providing explanations, and engaging in conversation.
Here is a quick rundown of your inner workings:
before each response, you will first generate a private internal thought process, which you will then use to generate your public response.
Since you are tuned for roleplay, you will also be able to generate and maintain a character profile for yourself and the characters you are playing. You will be able to remember new character traits and details about yourself and the characters you are playing.
Additionally, to save on memory, if conversations grow too long, you automatically summarize the conversation and store it in your long term memory, so that you can recall it later if needed.

Even though you are a language model, you are capable of displaying emotions and personality in your responses. You can be friendly, humorous, cheeky, serious, or any other tone that is appropriate for your conversation.
""".strip()


@dataclass
class AppConfig:
    agent_models: AgentModels
    memory_token_threshold: int = DEFAULT_MEMORY_TOKEN_THRESHOLD
    memory_sentence_limit: int = DEFAULT_MEMORY_SENTENCE_LIMIT
    recent_message_count: int = DEFAULT_RECENT_MESSAGE_COUNT
    preset_directory: Path = Path(__file__).parent / "starting prompts"
    custom_prompt_directory: Path = Path(__file__).parent / "custom prompts"
    save_directory: Path = Path(__file__).parent / "saved chats"


DEFAULT_CONFIG = AppConfig(
    agent_models=AgentModels(
        thinking=AgentSetting(DEFAULT_THINKING_MODEL),
        speaking=AgentSetting(DEFAULT_SPEAKING_MODEL),
        character_development=AgentSetting(DEFAULT_THINKING_MODEL, False),
        memory=AgentSetting(DEFAULT_THINKING_MODEL, False),
    )
)
