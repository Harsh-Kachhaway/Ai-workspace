import json
import requests
import websocket
import uuid
import os
import random
import gradio as gr

# --- BACKEND CONFIGURATION ---
COMFY_URL = "127.0.0.1:8190"
CLIENT_ID = str(uuid.uuid4())

# Point this to your Voice Cloning JSON file
JSON_RELATIVE_PATH = os.path.join("workflow", "voice_cloning.json")

# =====================================================================
# ⚠️ SIMPLIFIED 2-NODE SETUP: VERIFY IN YOUR JSON
# =====================================================================
QWEN_TTS_ID = "1"            # The Qwen TTS node handling text, audio, and generation
SAVE_AUDIO_ID = "7"  
AUDIO_LODER_ID = "2" # The Save Audio node for the final output
# =====================================================================

def clone_voice_generation(prompt_text, input_audio_path):
    # 1. Input Validation
    if not input_audio_path or not prompt_text:
        raise gr.Error("Missing required inputs. Please provide a reference audio file and a text prompt.")

    try:
        # 2. Upload reference audio to ComfyUI
        print(f"[Backend] Uploading audio file to ComfyUI: {input_audio_path}")
        with open(input_audio_path, "rb") as f:
            # We use "image" as the key because ComfyUI's default upload handler expects it, even for audio
            files = {"image": f} 
            upload_resp = requests.post(f"http://{COMFY_URL}/upload/image", files=files)
        
        if upload_resp.status_code != 200:
            raise gr.Error(f"Failed to upload audio to ComfyUI: {upload_resp.text}")
            
        uploaded_filename = upload_resp.json()["name"]

        # 3. Load Workflow JSON
        root_dir = os.path.dirname(os.path.dirname(__file__))
        json_path = os.path.join(root_dir, JSON_RELATIVE_PATH)
        
        with open(json_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        
        # 4. Inject Strings & Audio File directly into Qwen TTS
        # ⚠️ CRITICAL: Open your JSON and verify that "audio" and "text" are the exact names 
        # of the input fields on your Qwen TTS node.
        workflow[AUDIO_LODER_ID]["inputs"]["audio"] = uploaded_filename
        workflow[AUDIO_LODER_ID]["inputs"]["audioUI"] = f"/api/view?filename={uploaded_filename}&type=input&subfolder="
        workflow[QWEN_TTS_ID]["inputs"]["target_text"] = prompt_text

        # 5. Inject Random Seed into Qwen TTS
        new_seed = random.randint(1, 1125899906842624)
        print(f"[Backend] Generating audio with new random seed: {new_seed}")
        
        if "seed" in workflow[QWEN_TTS_ID]["inputs"]:
            workflow[QWEN_TTS_ID]["inputs"]["seed"] = new_seed
        elif "noise_seed" in workflow[QWEN_TTS_ID]["inputs"]:
            workflow[QWEN_TTS_ID]["inputs"]["noise_seed"] = new_seed

        # 6. Connect WebSocket and Queue
        ws = websocket.WebSocket()
        ws.connect(f"ws://{COMFY_URL}/ws?clientId={CLIENT_ID}")
        
        payload = {"prompt": workflow, "client_id": CLIENT_ID}
        prompt_resp = requests.post(f"http://{COMFY_URL}/prompt", json=payload)
        
        if prompt_resp.status_code != 200:
            ws.close()
            raise gr.Error(f"Error queueing workflow: {prompt_resp.text}")
        
        prompt_id = prompt_resp.json()["prompt_id"]
        print(f"[Backend] Audio job assigned tracking ID: {prompt_id}")

        # 7. Listen for execution to finish
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing' and message['data']['node'] is None:
                    break 
                    
        ws.close()
        print("[Backend] TTS processing complete. Fetching audio file...")

        # 8. Fetch Final Audio Output
        history_resp = requests.get(f"http://{COMFY_URL}/history/{prompt_id}").json()
        local_output_path = "voice_clone_output.wav"
        final_audio_saved = False

        if prompt_id in history_resp:
            outputs = history_resp[prompt_id].get("outputs", {})
            
            if SAVE_AUDIO_ID in outputs:
                media_list = outputs[SAVE_AUDIO_ID].get("audio", outputs[SAVE_AUDIO_ID].get("images", []))
                
                if media_list:
                    filename = media_list[0]["filename"]
                    subfolder = media_list[0]["subfolder"]
                    folder_type = media_list[0]["type"]

                    view_url = f"http://{COMFY_URL}/view"
                    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
                    audio_data = requests.get(view_url, params=params).content
                    
                    with open(local_output_path, "wb") as f:
                        f.write(audio_data)
                    final_audio_saved = True

        # 9. Final Output to Gradio
        if final_audio_saved:
            yield local_output_path
        else:
            raise gr.Error("ComfyUI finished, but failed to locate the final saved audio file.")
            
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Backend connection error: {str(e)}")