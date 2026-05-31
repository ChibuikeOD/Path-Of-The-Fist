
## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **Neo4j Database**: A local instance or [Neo4j Aura](https://neo4j.com/cloud/platform/aura-graph-database/) instance.

---

## 🛠️ Backend Setup (FastAPI)

1. **Navigate to the backend directory**:
   ```bash
   # From project root
   cd backend
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r ../requirements.txt
   ```

4. **Configure Environment Variables**:
   Create a `.env` file in the root directory (or use the existing one) and add your credentials:
   ```env
   # Neo4j
   NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_password

   # Start.gg API
   STARTGG_TOKEN=your_startgg_token

   # Chat provider for GraphRAG
   CHAT_PROVIDER=deepseek

   # DeepSeek (primary GraphRAG model)
   DEEPSEEK_API_KEY=your_deepseek_api_key
   DEEPSEEK_BASE_URL=https://api.deepseek.com
   DEEPSEEK_MODEL=deepseek-v4-pro

   # Hugging Face (optional fallback)
   HF_TOKEN=your_huggingface_token
   HF_ENDPOINT_URL=your_endpoint_url
   ```

5. **Sync Tournament Data**:
   The system can automatically fetch Combo Breaker data from `start.gg` and populate your Neo4j graph:
   ```bash
   python crud.py
   ```
   By default this syncs Combo Breaker 2022 through 2026.

6. **Start the FastAPI Server**:
   ```bash
   uvicorn main:app --reload
   ```
   The API will be available at `http://localhost:8000`.

---

## 💻 Frontend Setup (React + Vite)

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Start the development server**:
   ```bash
   npm run dev
   ```
   The application will be available at `http://localhost:5173`.

---



---
