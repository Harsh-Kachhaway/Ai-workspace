import json
import requests
import websocket
import uuid
import os
import io
import random  
from PIL import Image
import gradio as gr

# --- BACKEND CONFIGURATION ---
COMFY_URL = "127.0.0.1:8190"
CLIENT_ID = str(uuid.uuid4())
JSON_RELATIVE_PATH = os.path.join("workflow", "inpaint_workflow.json")

# =====================================================================
# ⚠️ CRITICAL: YOU MUST VERIFY THESE IDs IN YOUR JSON FILE
# =====================================================================
LOAD_IMAGE_ID = "1"       
SAVE_IMAGE_ID = "9"      
POSITIVE_PROMPT_ID = "4"   # Check your JSON: Is this actually your Positive CLIP Text Encode?
NEGATIVE_PROMPT_ID = "5"   # Check your JSON: Is this actually your Negative CLIP Text Encode?
SAM3_PROMPT_ID = "13"
KSAMPLER_ID = "3"         # --- NEW: ID for your KSampler node
# =====================================================================

def inpaint_generation_from_image(positive_prompt_text, negative_prompt_text, input_image_path, sam_prompt_text):
    if not input_image_path or not positive_prompt_text or not sam_prompt_text:
        raise gr.Error("Missing required inputs. Please provide an image, a positive prompt, and a SAM prompt.")

    try:
        # Uploading file to ComfyUI
        print(f"[Backend] Uploading file to ComfyUI: {input_image_path}")
        with open(input_image_path, "rb") as f:
            files = {"image": f}
            upload_resp = requests.post(f"http://{COMFY_URL}/upload/image", files=files)
        
        if upload_resp.status_code != 200:
            raise gr.Error(f"Failed to upload image to ComfyUI: {upload_resp.text}")
            
        uploaded_filename = upload_resp.json()["name"]

        # Load Workflow JSON
        root_dir = os.path.dirname(os.path.dirname(__file__))
        json_path = os.path.join(root_dir, JSON_RELATIVE_PATH)
        
        with open(json_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        
        # --- INJECT TEXT PARAMETERS ---
        workflow[LOAD_IMAGE_ID]["inputs"]["image"] = uploaded_filename
        workflow[POSITIVE_PROMPT_ID]["inputs"]["text"] = positive_prompt_text
        workflow[NEGATIVE_PROMPT_ID]["inputs"]["text"] = negative_prompt_text
        workflow[SAM3_PROMPT_ID]["inputs"]["text"] = sam_prompt_text

        # --- INJECT RANDOM SEED ---
        # Generate a random integer (ComfyUI seeds can be up to 15-16 digits long)
        new_seed = random.randint(1, 1125899906842624)
        print(f"[Backend] Generating with new random seed: {new_seed}")
        
        # Note: Depending on your KSampler, the input might be named "seed" or "noise_seed"
        if "seed" in workflow[KSAMPLER_ID]["inputs"]:
            workflow[KSAMPLER_ID]["inputs"]["seed"] = new_seed
        elif "noise_seed" in workflow[KSAMPLER_ID]["inputs"]:
            workflow[KSAMPLER_ID]["inputs"]["noise_seed"] = new_seed

        # Connect WebSocket and send to ComfyUI queue
        ws = websocket.WebSocket()
        ws.connect(f"ws://{COMFY_URL}/ws?clientId={CLIENT_ID}")
        
        payload = {"prompt": workflow, "client_id": CLIENT_ID}
        prompt_resp = requests.post(f"http://{COMFY_URL}/prompt", json=payload)
        
        if prompt_resp.status_code != 200:
            ws.close()
            raise gr.Error(f"Error queueing workflow: {prompt_resp.text}")
        
        prompt_id = prompt_resp.json()["prompt_id"]

        # Listen for updates from ComfyUI
        while True:
            out = ws.recv()
            if isinstance(out, bytes):
                if len(out) > 8:
                    image_bytes = out[8:] 
                    try:
                        yield Image.open(io.BytesIO(image_bytes))
                    except Exception:
                        pass
            elif isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing' and message['data']['node'] is None:
                    break 
                    
        ws.close()

        # Fetch final image
        history_resp = requests.get(f"http://{COMFY_URL}/history/{prompt_id}").json()
        local_output_path = "t2i_studio_output.png"
        final_image_saved = False

        if prompt_id in history_resp:
            outputs = history_resp[prompt_id].get("outputs", {})
            if SAVE_IMAGE_ID in outputs:
                images_list = outputs[SAVE_IMAGE_ID].get("images", [])
                if images_list:
                    filename = images_list[0]["filename"]
                    subfolder = images_list[0]["subfolder"]
                    folder_type = images_list[0]["type"]

                    view_url = f"http://{COMFY_URL}/view"
                    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
                    img_data_resp = requests.get(view_url, params=params)
                    
                    with open(local_output_path, "wb") as f:
                        f.write(img_data_resp.content)
                    final_image_saved = True

        if final_image_saved:
            yield local_output_path
        else:
            raise gr.Error("ComfyUI finished, but failed to locate the final saved image.")
            
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Backend connection error: {str(e)}")