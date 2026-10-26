import json
import requests
import websocket
import uuid
import os
import random  

# --- BACKEND CONFIGURATION ---
COMFY_URL = "127.0.0.1:8190"
CLIENT_ID = str(uuid.uuid4())

# 1. Update this to point precisely to your new folder layout filename
JSON_RELATIVE_PATH = os.path.join("workflow", "florence_workflow.json")

LOAD_IMAGE_ID = "20"       
DISPLAY_ANY_ID = "22"   
KSAMPLER_ID ="18"   

def extract_prompt_from_image(input_image_path):
    if not input_image_path:
        yield "Error: No image source provided."
        return

    try:
        # Uploading file to ComfyUI
        print(f"[Backend] Uploading file to ComfyUI: {input_image_path}")
        with open(input_image_path, "rb") as f:
            files = {"image": f}
            upload_resp = requests.post(f"http://{COMFY_URL}/upload/image", files=files)
        
        if upload_resp.status_code != 200:
            yield f"Error uploading image to ComfyUI: {upload_resp.text}"
            return
            
        uploaded_filename = upload_resp.json()["name"]

        # 2. DYNAMIC PATH RESOLUTION:
        # os.path.dirname(os.path.dirname(__file__)) takes us up to the root 'multimedia_studio' folder.
        # Then we append the path to find 'workflows/florence_workflow.json'.
        root_dir = os.path.dirname(os.path.dirname(__file__))
        json_path = os.path.join(root_dir, JSON_RELATIVE_PATH)
        
        print(f"[Backend] Looking for JSON at: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        
        # Inject the server filename string into your Load Image node
        workflow[LOAD_IMAGE_ID]["inputs"]["image"] = uploaded_filename
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
            yield f"Error queueing workflow: {prompt_resp.text}"
            return
            
        # yield "Processing image analysis (Florence-2)..."

        # Listen for updates from ComfyUI
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                
                if message['type'] == 'executed' and message['data']['node'] == DISPLAY_ANY_ID:
                    node_output = message['data']['output']
                    if "text" in node_output and len(node_output["text"]) > 0:
                        yield node_output["text"][0]
                
                if message['type'] == 'executing' and message['data']['node'] is None:
                    break
                    
        ws.close()

    except Exception as e:
        yield f"Backend connection error occurred: {str(e)}"