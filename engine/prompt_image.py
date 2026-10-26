import json
import requests
import websocket
import uuid
import os
import io
from PIL import Image
import random  


# --- BACKEND CONFIGURATION ---
COMFY_URL = "127.0.0.1:8190"
CLIENT_ID = str(uuid.uuid4())
JSON_RELATIVE_PATH = os.path.join("workflow", "prompt_image.json")

# Update these strings to match the exact Node IDs inside your t2i_workflow.json
POSITIVE_PROMPT_ID = "3"     # CLIP Text Encode (Positive)
NEGATIVE_PROMPT_ID = "4"     # CLIP Text Encode (Negative)
SAVE_IMAGE_ID = "7"          # Final Save Image Node ID
KSAMPLER_ID = "2"
def generate_image_from_text(positive_prompt_text, negative_prompt_text):
    """
    Pure backend utility function. Modifies inputs in the text-to-image JSON,
    streams raw binary KSampler previews, and yields the final high-res file path.
    """
    if not positive_prompt_text:
        yield None
        return

    try:
        # 1. Resolve path and load the workflow API file dynamically
        root_dir = os.path.dirname(os.path.dirname(__file__))
        json_path = os.path.join(root_dir, JSON_RELATIVE_PATH)
        
        print(f"[Backend] Reading Text-to-Image Workflow from: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        
        # 2. Inject both prompt strings directly into their respective nodes
        workflow[POSITIVE_PROMPT_ID]["inputs"]["text"] = positive_prompt_text
        workflow[NEGATIVE_PROMPT_ID]["inputs"]["text"] = negative_prompt_text

         # --- INJECT RANDOM SEED ---
        # Generate a random integer (ComfyUI seeds can be up to 15-16 digits long)
        new_seed = random.randint(1, 1125899906842624)
        print(f"[Backend] Generating with new random seed: {new_seed}")
        
        # Note: Depending on your KSampler, the input might be named "seed" or "noise_seed"
        if "seed" in workflow[KSAMPLER_ID]["inputs"]:
            workflow[KSAMPLER_ID]["inputs"]["seed"] = new_seed
        elif "noise_seed" in workflow[KSAMPLER_ID]["inputs"]:
            workflow[KSAMPLER_ID]["inputs"]["noise_seed"] = new_seed
            
        # 3. Establish a persistent WebSocket data stream connection
        ws = websocket.WebSocket()
        ws.connect(f"ws://{COMFY_URL}/ws?clientId={CLIENT_ID}")
        
        # 4. Fire execution payload object over to the processing engine
        payload = {"prompt": workflow, "client_id": CLIENT_ID}
        prompt_resp = requests.post(f"http://{COMFY_URL}/prompt", json=payload)
        
        if prompt_resp.status_code != 200:
            ws.close()
            print(f"[Backend Error] Failed to queue prompt: {prompt_resp.text}")
            return
            
        prompt_id = prompt_resp.json()["prompt_id"]
        print(f"[Backend] Job successfully assigned tracking ID: {prompt_id}")

        # 5. Continuous multi-stream execution network loop listener
        while True:
            out = ws.recv()
            
            # Action A: Intercept raw live binary preview chunks from KSampler
            if isinstance(out, bytes):
                if len(out) > 8:
                    # Strip ComfyUI's 8-byte messaging protocol tracking headers
                    image_bytes = out[8:] 
                    try:
                        # Convert binary stream directly into an active viewable PIL object
                        preview_frame = Image.open(io.BytesIO(image_bytes))
                        # Yield the frame straight to the UI canvas view
                        yield preview_frame
                    except Exception:
                        pass # Bypass imperfectly constructed intermediate packets

            # Action B: Monitor string messages to confirm overall process state
            elif isinstance(out, str):
                message = json.loads(out)
                
                # Check if the global pipeline dropped back to an idle state
                if message['type'] == 'executing' and message['data']['node'] is None:
                    break 
                    
        ws.close()
        print("[Backend] Denoising pass complete. Fetching clean HD render file asset...")

        # 6. Retrieve the complete final full-quality image from history
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

                    # Pull high-resolution raw data payload from server cache directory
                    view_url = f"http://{COMFY_URL}/view"
                    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
                    img_data_resp = requests.get(view_url, params=params)
                    
                    # Overwrite and dump locally for frontend access
                    with open(local_output_path, "wb") as f:
                        f.write(img_data_resp.content)
                    final_image_saved = True

        # Final yield swaps out the last pixelated render step for the permanent asset file
        if final_image_saved:
            yield local_output_path
        else:
            print("[Backend Error] High-resolution rendering file sync dropped.")

    except Exception as e:
        print(f"[Backend System Crash Alert] {str(e)}")
        yield None