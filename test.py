from agents import CustomAgent
test = CustomAgent("test","say ONLY test","qwen3:8b")
output = test._insert_system_prompt_arguments("this is a test. In the following there should be 'Hello World'. ${{testVar}}", {"testVar": "Hello World"})
print(output)