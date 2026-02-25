# LM Studio Setup Guide

Complete guide for setting up a local LLM using LM Studio for the NLP MongoDB Interface.

## What is LM Studio?

LM Studio is a desktop application that allows you to run Large Language Models (LLMs) locally on your computer. This means:
- ✅ **100% Free** - No API costs
- ✅ **Unlimited Queries** - No rate limits
- ✅ **Privacy** - Your data never leaves your machine
- ✅ **Offline Capable** - Works without internet (after model download)

## System Requirements

### Minimum Requirements
- **RAM**: 8GB (for Llama 3 8B or Mistral 7B)
- **Storage**: 10GB free space
- **OS**: Windows 10/11, macOS 10.15+, or Linux

### Recommended Requirements
- **RAM**: 16GB or more
- **GPU**: NVIDIA GPU with 6GB+ VRAM (optional, but 10x faster)
- **Storage**: 20GB free space

## Installation Steps

### 1. Download LM Studio

1. Visit https://lmstudio.ai/
2. Download for your operating system:
   - Windows: `LMStudio-Setup.exe`
   - macOS: `LMStudio.dmg`
   - Linux: `LMStudio.AppImage`
3. Install the application

### 2. Download a Model

**Recommended Models:**

#### For 8GB RAM:
- **Phi-3 Mini 4K Instruct** (3.8GB)
  - Search: `microsoft/Phi-3-mini-4k-instruct-gguf`
  - Quantization: `Q4_K_M`
  - Best for: Limited RAM, fast responses

#### For 16GB RAM:
- **Mistral 7B Instruct v0.2** (4.4GB)
  - Search: `TheBloke/Mistral-7B-Instruct-v0.2-GGUF`
  - Quantization: `Q4_K_M`
  - Best for: Balance of quality and speed

- **Meta Llama 3 8B Instruct** (4.7GB)
  - Search: `QuantFactory/Meta-Llama-3-8B-Instruct-GGUF`
  - Quantization: `Q4_K_M`
  - Best for: Highest quality responses

**Download Steps:**
1. Open LM Studio
2. Click "Search" tab
3. Search for model name (e.g., "llama-3-8b-instruct")
4. Find GGUF format version
5. Select quantization: **Q4_K_M** (recommended)
6. Click "Download"
7. Wait for download to complete (5-10 minutes)

### 3. Start Local Server

1. Click "Local Server" tab in LM Studio
2. Select your downloaded model from dropdown
3. Click "Start Server"
4. Server will start on `http://localhost:1234`
5. Keep LM Studio running while using the application

### 4. Test Connection

Open terminal/command prompt and test:

```bash
curl http://localhost:1234/v1/models
```

You should see a JSON response with your loaded model.

### 5. Configure NLP Service

Edit `nlp-service/.env`:

```env
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://localhost:1234/v1
LOCAL_LLM_MODEL=llama-3-8b-instruct
```

**Important:** Use the exact model name shown in LM Studio.

### 6. Start Application

```bash
# Start NLP service
cd nlp-service
python main.py

# In another terminal, start backend
cd backend
npm run dev

# In another terminal, start frontend
cd frontend
npm run dev
```

## Using with Docker

If running the application in Docker, use `host.docker.internal` to access LM Studio on the host machine:

```env
LOCAL_LLM_BASE_URL=http://host.docker.internal:1234/v1
```

## Troubleshooting

### Model Not Loading
- **Issue**: Model fails to load in LM Studio
- **Solution**: Ensure you have enough RAM. Try a smaller model (Phi-3 Mini).

### Connection Refused
- **Issue**: `ECONNREFUSED` error when connecting
- **Solution**: 
  - Ensure LM Studio server is running
  - Check port 1234 is not blocked by firewall
  - Verify URL is `http://localhost:1234/v1`

### Slow Responses
- **Issue**: Queries take 30+ seconds
- **Solution**:
  - Use GPU acceleration if available (Settings → GPU)
  - Try a smaller model
  - Reduce context window in LM Studio settings

### Out of Memory
- **Issue**: System runs out of RAM
- **Solution**:
  - Close other applications
  - Use a smaller quantization (Q3_K_M instead of Q4_K_M)
  - Try Phi-3 Mini model

## Model Comparison

| Model | Size | RAM Needed | Quality | Speed | Best For |
|-------|------|------------|---------|-------|----------|
| Phi-3 Mini | 3.8GB | 8GB | Good | Fast | Limited resources |
| Mistral 7B | 4.4GB | 12GB | Very Good | Medium | Balanced |
| Llama 3 8B | 4.7GB | 16GB | Excellent | Medium | Best quality |

## Performance Tips

1. **Enable GPU Acceleration**
   - Settings → GPU → Enable
   - Requires NVIDIA GPU with CUDA support

2. **Adjust Context Window**
   - Smaller context = faster responses
   - Recommended: 2048 tokens

3. **Use Quantized Models**
   - Q4_K_M is the sweet spot
   - Q3_K_M for lower RAM
   - Q5_K_M for better quality (more RAM)

## Next Steps

Once LM Studio is running:
1. Test with a simple query: "Show movies from 1999"
2. Monitor response times
3. Adjust settings if needed
4. Compare with Gemini/OpenAI if available

## Additional Resources

- LM Studio Documentation: https://lmstudio.ai/docs
- Model Hub: https://huggingface.co/models
- Community Discord: https://discord.gg/lmstudio
