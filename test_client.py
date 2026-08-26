import httpx
import json
import sys

def chat_with_controlplane():
    print("Welcome to your Secure AI Assistant (Powered by ControlPlane.ai)")
    print("Type 'quit' to exit.\n")
    
    # We use httpx to talk to our local proxy instead of api.openai.com
    client = httpx.Client(base_url="http://localhost:8000/v1")
    
    # Let's pretend we are building a customer support bot
    headers = {
        "X-ControlPlane-Profile": "customer_support"
    }

    while True:
        user_input = input("You: ")
        if user_input.lower() in ['quit', 'exit']:
            break
            
        payload = {
            "model": "mock", # Our local mock model
            "messages": [{"role": "user", "content": user_input}],
            "stream": True
        }

        print("Assistant: ", end="", flush=True)
        
        try:
            with client.stream("POST", "/chat/completions", json=payload, headers=headers) as response:
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    print(delta["content"], end="", flush=True)
                        except json.JSONDecodeError:
                            pass
            print("\n")
        except Exception as e:
            print(f"\n[Error connecting to ControlPlane: {e}]\n")

if __name__ == "__main__":
    chat_with_controlplane()
