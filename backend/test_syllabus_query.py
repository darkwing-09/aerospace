import asyncio
from model_service import ModelService
from agent_orchestrator import multi_agent_orchestrator

async def run_test():
    model_svc = ModelService()
    await model_svc.load_model()
    
    messages = [{"role": "user", "content": "What is the Machine Learning syllabus?"}]
    print("=== STARTING SYLLABUS QUERY TEST ===")
    
    collected_tokens = []
    async for event in multi_agent_orchestrator.execute_query_stream("DA_2026_Syllabus.pdf", messages, model_svc):
        if event.startswith("data: "):
            content = event[6:-2]
            if not content.startswith("["):
                decoded = content.replace("\\n", "\n")
                collected_tokens.append(decoded)
                print(decoded, end="", flush=True)
                
    full_text = "".join(collected_tokens)
    print("\n\n=== FULL GENERATED RESPONSE ===")
    print(full_text)
    print("=== TEST COMPLETED ===")

if __name__ == "__main__":
    asyncio.run(run_test())
