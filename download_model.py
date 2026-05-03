import os
import argparse
from huggingface_hub import snapshot_download

def main():
    parser = argparse.ArgumentParser(description="Download AeroMind Model weights")
    parser.add_argument("--token", required=True, help="Your HuggingFace Read Token")
    parser.add_argument("--model", default="varundevmishra09/My_Model", help="Model ID")
    parser.add_argument("--dest", default="./backend/models/", help="Destination folder")
    
    args = parser.parse_args()
    
    print(f"🚀 Initializing download for: {args.model}")
    print(f"📍 Destination: {os.path.abspath(args.dest)}")
    
    try:
        snapshot_download(
            repo_id=args.model,
            token=args.token,
            local_dir=args.dest,
            local_dir_use_symlinks=False,
            resume_download=True
        )
        print("\n✅ Download Complete!")
        print("\nNext steps:")
        print("1. Update HF_TOKEN in aeromind/backend/.env")
        print("2. Run the backend: cd backend && uvicorn main:app --reload")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
