# 🚀 AI Creative Workspace 

![Status](https://img.shields.io/badge/Status-Prototype-blue)
![Architecture](https://img.shields.io/badge/Architecture-Local_Inference-success)
![Cost](https://img.shields.io/badge/API_Costs-$0-brightgreen)

A unified, local-first multimodal AI platform combining advanced image and audio generation into a single, minimal web interface. 
### 📸 Live Demo
[![Watch the NLP-to-SQL Demo](https://github.com/Harsh-Kachhaway/Ai-workspace/blob/main/Screenshot%202026-10-26%20172028.png)](https://lnkd.in/p/dGpVyXRU)

*Click the image above to watch the full working demo on LinkedIn.*

### 🎯 The Goal: Zero-Cost, Uncapped AI
Relying on external AI services introduces token limits, pay-per-generation models, and high API overhead. This project was built to solve that by running **100% on local hardware**. 
- 🚫 No token limits
- 🚫 No API costs or subscriptions
- 🔒 Complete data privacy and local execution

## ✨ Core Features

### 🎨 Image Generation & Processing
* **6 Custom Image Workflows:** Ranging from basic text-to-image to advanced generation pipelines.
* **AI Inpainting:** Modify, fix, or replace specific elements within existing images locally.
* **Image Analysis:** Automated visual extraction and context understanding.

### 🎵 Audio & Voice
* **Audio Generation:** Multiple distinct workflows for synthesizing audio from text or prompts.
* **Voice Workflows:** Dedicated pipelines for voice generation and processing.

### 🧠 Prompt Engineering
* **Extraction & Enhancement:** Built-in tools to extract prompts from existing media or enhance short user prompts into highly detailed instructions for the models.

## 🏗️ System Architecture
The system is built using a decoupled architecture to ensure smooth UI performance while heavy tensor operations run in the background:
1. **The Web/Backend Layer:** Manages the clean, minimal user interface and handles user interactions without blocking.
2. **The Local AI Engine:** A dedicated local inference environment that queues and executes the heavy image and audio workflows on local GPU hardware.

---

### 💻 Tech Stack Highlights
* **Inference:** Local AI Models (Image & Audio)
* **Backend:** Custom backend handling workflow routing and API bridging
* **Frontend:** Minimalist UI/UX for complex AI node workflows

---
*Note: A public live demo was temporarily hosted for 48 hours for beta testing. The code here represents the local deployment architecture.*
