#!/bin/bash

# AeroMind Setup Script
echo "🛫 Initializing AeroMind Environment..."

# 1. Backend Setup
echo "📦 Setting up Python backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cd ..

# 2. Frontend Setup
echo "📦 Setting up React frontend..."
cd frontend
npm install
cd ..

# 3. Create necessary dirs
mkdir -p backend/models
mkdir -p backend/pdfs

echo "✅ Setup Complete!"
echo ""
echo "Follow these steps to start:"
echo "1. Put your HF_TOKEN in backend/.env"
echo "2. Place mig21bis.pdf in backend/pdfs/"
echo "3. Run: cd backend && uvicorn main:app --reload"
echo "4. In another terminal: cd frontend && npm run dev"
