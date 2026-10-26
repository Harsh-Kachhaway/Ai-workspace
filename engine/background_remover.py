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
JSON_RELATIVE_PATH = os.path.join("workflow", "background_remover.json")

# =====================================================================
# ⚠️ CRITICAL: YOU MUST VERIFY THESE IDs IN YOUR JSON FILE
# =====================================================================
LOAD_IMAGE_ID = "4"       
SAVE_IMAGE_ID = "9"  
SAVE_CROPED_IMAGE_ID = "17" # <-- UPDATE THIS with the actual Node ID for the cropped image      
PROMPT_ID = "3"  
SAM3_PROMPT_ID = "2"
# =====================================================================

def background_remover_from_image(prompt_text, input_image_path):
    if not input_image_path or not prompt_text:
        raise gr.Error("Missing required inputs. Please provide an image and a prompt.")

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
        workflow[PROMPT_ID]["inputs"]["text"] = prompt_text
     
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
                        preview = Image.open(io.BytesIO(image_bytes))
                        # Yield the preview for the first image, and None for the second
                        yield (preview, None) 
                    except Exception:
                        pass
            elif isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing' and message['data']['node'] is None:
                    break 
                    
        ws.close()

        # Fetch final images
        history_resp = requests.get(f"http://{COMFY_URL}/history/{prompt_id}").json()
        
        local_output_path_1 = "t2i_studio_output.png"
        local_output_path_2 = "t2i_studio_cropped.png"
        
        final_image_saved = False
        cropped_image_saved = False

        if prompt_id in history_resp:
            outputs = history_resp[prompt_id].get("outputs", {})
            
            # --- FETCH FIRST IMAGE ---
            if SAVE_IMAGE_ID in outputs:
                images_list = outputs[SAVE_IMAGE_ID].get("images", [])
                if images_list:
                    filename = images_list[0]["filename"]
                    subfolder = images_list[0]["subfolder"]
                    folder_type = images_list[0]["type"]

                    view_url = f"http://{COMFY_URL}/view"
                    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
                    img_data_resp = requests.get(view_url, params=params)
                    
                    with open(local_output_path_1, "wb") as f:
                        f.write(img_data_resp.content)
                    final_image_saved = True

            # --- FETCH SECOND (CROPPED) IMAGE ---
            if SAVE_CROPED_IMAGE_ID in outputs:
                images_list_2 = outputs[SAVE_CROPED_IMAGE_ID].get("images", [])
                if images_list_2:
                    filename_2 = images_list_2[0]["filename"]
                    subfolder_2 = images_list_2[0]["subfolder"]
                    folder_type_2 = images_list_2[0]["type"]

                    view_url_2 = f"http://{COMFY_URL}/view"
                    params_2 = {"filename": filename_2, "subfolder": subfolder_2, "type": folder_type_2}
                    img_data_resp_2 = requests.get(view_url_2, params=params_2)
                    
                    with open(local_output_path_2, "wb") as f:
                        f.write(img_data_resp_2.content)
                    cropped_image_saved = True

        # Return both images if successful
        if final_image_saved and cropped_image_saved:
            yield (local_output_path_1, local_output_path_2)
        elif final_image_saved:
            yield (local_output_path_1, None)  # Fallback if only the first one generated
        else:
            raise gr.Error("ComfyUI finished, but failed to locate the final saved images.")
            
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Backend connection error: {str(e)}")