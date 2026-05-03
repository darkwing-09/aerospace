import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from config import settings

def test():
    print("Testing model loading...")
    model_id = settings.HF_MODEL_ID
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, 
        trust_remote_code=True, 
        device_map="auto",
        torch_dtype=torch.float32
    )
    
    prompt = "### Instruction:\nAircraft: MIG-21BIS\nHello\n\n### Response:\n"
    inputs = tokenizer(prompt, return_tensors="pt")
    
    print("Generating...")
    outputs = model.generate(**inputs, max_new_tokens=10)
    print("Result:", tokenizer.decode(outputs[0], skip_special_tokens=True))

if __name__ == "__main__":
    test()
