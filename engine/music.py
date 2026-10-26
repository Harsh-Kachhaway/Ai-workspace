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

# Point this to your Music Generation JSON file
JSON_RELATIVE_PATH = os.path.join("workflow", "music.json")

# =====================================================================
# ⚠️ CRITICAL IDs: VERIFY IN YOUR JSON
# =====================================================================
PROMPT_ID = "5"        # The CLIP Text Encode node for your music prompt
KSAMPLER_ID = "4"      # The KSampler (or equivalent sampler) for generation
SAVE_AUDIO_ID = "24"    # The node that saves the final audio output
# =====================================================================

def generate_music_from_text(music_prompt_text):
    # 1. Input Validation
    if not music_prompt_text:
        raise gr.Error("Please provide a prompt describing the music you want to generate.")

    try:
        # 2. Load Workflow JSON
        root_dir = os.path.dirname(os.path.dirname(__file__))
        json_path = os.path.join(root_dir, JSON_RELATIVE_PATH)
        
        with open(json_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        
        # 3. Inject Text Parameter
        # ⚠️ Verify that "text" is the correct input key for your CLIP Text Encode node
        workflow[PROMPT_ID]["inputs"]["text"] = music_prompt_text

        # 4. Inject Random Seed into KSampler
        new_seed = random.randint(1, 1125899906842624)
        print(f"[Backend] Generating music with random seed: {new_seed}")
        
        # Depending on the node, it might use 'seed' or 'noise_seed'
        if "seed" in workflow[KSAMPLER_ID]["inputs"]:
            workflow[KSAMPLER_ID]["inputs"]["seed"] = new_seed
        elif "noise_seed" in workflow[KSAMPLER_ID]["inputs"]:
            workflow[KSAMPLER_ID]["inputs"]["noise_seed"] = new_seed

        # 5. Connect WebSocket and Queue
        ws = websocket.WebSocket()
        ws.connect(f"ws://{COMFY_URL}/ws?clientId={CLIENT_ID}")
        
        payload = {"prompt": workflow, "client_id": CLIENT_ID}
        prompt_resp = requests.post(f"http://{COMFY_URL}/prompt", json=payload)
        
        if prompt_resp.status_code != 200:
            ws.close()
            raise gr.Error(f"Error queueing workflow: {prompt_resp.text}")
        
        prompt_id = prompt_resp.json()["prompt_id"]

        # 6. Listen for execution to finish
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing' and message['data']['node'] is None:
                    break 
                    
        ws.close()
        print("[Backend] Music generation complete. Fetching audio file...")

        # 7. Fetch Final Audio Output
        history_resp = requests.get(f"http://{COMFY_URL}/history/{prompt_id}").json()
        local_output_path = "generated_music_output.wav"
        final_audio_saved = False

        if prompt_id in history_resp:
            outputs = history_resp[prompt_id].get("outputs", {})
            
            if SAVE_AUDIO_ID in outputs:
                # Check both "audio" and "images" keys (some custom nodes save audio under "images")
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

        # 8. Final Output to Gradio
        if final_audio_saved:
            yield local_output_path
        else:
            raise gr.Error("ComfyUI finished, but failed to locate the final saved audio file.")
            
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Backend connection error: {str(e)}")