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

# Point this to your new OpenPose JSON file
JSON_RELATIVE_PATH = os.path.join("workflow", "Controlnet.json")

# =====================================================================
# ⚠️ CRITICAL: YOU MUST VERIFY THESE IDs IN YOUR JSON FILE
# =====================================================================
LOAD_IMAGE_ID = "11"         # The node where you load the base image
POSITIVE_PROMPT_ID = "2"    # Your Positive CLIP Text Encode
NEGATIVE_PROMPT_ID = "6"    # Your Negative CLIP Text Encode
KSAMPLER_ID = "4"          # The KSampler node (for injecting the random seed)
SAVE_IMAGE_ID = "8"         # The Save Image node for the FINAL render
OPENPOSE_PREVIEW_ID = "12"  # The Preview Image/Save Image node attached to the OpenPose preprocessor
# =====================================================================

def controlnet_openpose_generation(positive_prompt_text, negative_prompt_text, input_image_path):
    if not input_image_path or not positive_prompt_text:
        raise gr.Error("Missing required inputs. Please provide a reference image and a positive prompt.")

    try:
        # 1. Upload reference image to ComfyUI
        print(f"[Backend] Uploading reference file to ComfyUI: {input_image_path}")
        with open(input_image_path, "rb") as f:
            files = {"image": f}
            upload_resp = requests.post(f"http://{COMFY_URL}/upload/image", files=files)
        
        if upload_resp.status_code != 200:
            raise gr.Error(f"Failed to upload image to ComfyUI: {upload_resp.text}")
            
        uploaded_filename = upload_resp.json()["name"]

        # 2. Load Workflow JSON
        root_dir = os.path.dirname(os.path.dirname(__file__))
        json_path = os.path.join(root_dir, JSON_RELATIVE_PATH)
        
        with open(json_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        
        # 3. Inject Strings & Image
        workflow[LOAD_IMAGE_ID]["inputs"]["image"] = uploaded_filename
        workflow[POSITIVE_PROMPT_ID]["inputs"]["text"] = positive_prompt_text
        workflow[NEGATIVE_PROMPT_ID]["inputs"]["text"] = negative_prompt_text

        # 4. Inject Random Seed into KSampler
        new_seed = random.randint(1, 1125899906842624)
        print(f"[Backend] Generating with new random seed: {new_seed}")
        
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

        # 6. Stream Previews
        while True:
            out = ws.recv()
            if isinstance(out, bytes):
                if len(out) > 8:
                    image_bytes = out[8:] 
                    try:
                        preview = Image.open(io.BytesIO(image_bytes))
                        # Yield the KSampler preview to the first image slot, leave the second blank for now
                        yield (preview, None) 
                    except Exception:
                        pass
            elif isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing' and message['data']['node'] is None:
                    break 
                    
        ws.close()

        # 7. Fetch Final High-Res Outputs
        history_resp = requests.get(f"http://{COMFY_URL}/history/{prompt_id}").json()
        
        final_render_path = "controlnet_output_render.png"
        openpose_map_path = "controlnet_output_pose.png"
        
        final_image_saved = False
        pose_image_saved = False

        if prompt_id in history_resp:
            outputs = history_resp[prompt_id].get("outputs", {})
            
            # --- FETCH FINAL RENDER ---
            if SAVE_IMAGE_ID in outputs:
                images_list = outputs[SAVE_IMAGE_ID].get("images", [])
                if images_list:
                    filename = images_list[0]["filename"]
                    subfolder = images_list[0]["subfolder"]
                    folder_type = images_list[0]["type"]

                    view_url = f"http://{COMFY_URL}/view"
                    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
                    img_data = requests.get(view_url, params=params).content
                    
                    with open(final_render_path, "wb") as f:
                        f.write(img_data)
                    final_image_saved = True

            # --- FETCH OPENPOSE MAP ---
            if OPENPOSE_PREVIEW_ID in outputs:
                images_list_2 = outputs[OPENPOSE_PREVIEW_ID].get("images", [])
                if images_list_2:
                    filename_2 = images_list_2[0]["filename"]
                    subfolder_2 = images_list_2[0]["subfolder"]
                    folder_type_2 = images_list_2[0]["type"]

                    view_url_2 = f"http://{COMFY_URL}/view"
                    params_2 = {"filename": filename_2, "subfolder": subfolder_2, "type": folder_type_2}
                    img_data_2 = requests.get(view_url_2, params=params_2).content
                    
                    with open(openpose_map_path, "wb") as f:
                        f.write(img_data_2)
                    pose_image_saved = True

        # 8. Final Output to Gradio
        if final_image_saved and pose_image_saved:
            yield (final_render_path, openpose_map_path)
        elif final_image_saved:
            print("[Backend Warning] OpenPose map was not found. Yielding only final render.")
            yield (final_render_path, None)
        else:
            raise gr.Error("ComfyUI finished, but failed to locate the final saved images.")
            
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Backend connection error: {str(e)}")