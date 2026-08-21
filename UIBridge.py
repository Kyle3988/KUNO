class UIBridge:
    """Interface exposed by the UI. The AI Engine calls these methods to render UI updates."""

    async def on_user_message(self, text: str): pass
    async def on_agent_chunk(self, agent_name: str, chunk: str): pass
    async def on_agent_result(self, agent_name: str, result: str): pass
    async def on_phase_complete(self): pass
    async def on_complete(self): pass
    async def on_error(self, error_msg: str): pass