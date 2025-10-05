import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2 import service_account
from PIL import Image
import io, os, re

# --- Authentication ---
# Try to use Streamlit secrets (for deployment), fall back to local file (for testing)
try:
    # Streamlit Cloud deployment
    creds_dict = st.secrets["google_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    FOLDER_ID = st.secrets["drive"]["folder_id"]
except:
    # Local testing
    SERVICE_ACCOUNT_FILE = "credentials.json"
    FOLDER_ID = "0AGhLT2zlih_HUk9PVA"
    
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )

service = build("drive", "v3", credentials=creds)

# --- Utility functions ---
def sanitize_filename(name: str) -> str:
    """Remove spaces & special chars."""
    return re.sub(r"[^A-Za-z0-9_-]", "", name.replace(" ", "_"))

def compress_image(file) -> str:
    """Compress image under 50 KB and return temp path."""
    image = Image.open(file).convert("RGB")
    temp_path = "temp.jpg"
    
    # Get original dimensions
    width, height = image.size
    
    # Start with original size and quality
    new_width, new_height = width, height
    quality = 85
    scale_factor = 1.0
    
    # First try just compressing without resizing
    image.save(temp_path, "JPEG", optimize=True, quality=quality)
    
    # If still too large, start resizing and compressing
    while os.path.getsize(temp_path) >= 50_000 and quality >= 10:
        # Reduce quality first
        quality -= 5
        image.save(temp_path, "JPEG", optimize=True, quality=quality)
        
        # If still too large after minimum quality, start reducing size
        if os.path.getsize(temp_path) >= 50_000 and quality <= 10:
            scale_factor *= 0.8  # Reduce to 80% each time
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            resized_image = image.resize((new_width, new_height), Image.LANCZOS)
            resized_image.save(temp_path, "JPEG", optimize=True, quality=quality)
            
            # Reset quality to try again with smaller image
            quality = 30
    
    return temp_path

def upload_to_drive(local_path, filename):
    meta = {"name": filename, "parents": [FOLDER_ID]}
    media = MediaFileUpload(local_path, mimetype="image/jpeg")
    file = service.files().create(
        body=meta, 
        media_body=media, 
        fields="id",
        supportsAllDrives=True
    ).execute()
    return file.get("id")

def find_file_id(filename):
    results = service.files().list(
        q=f"name='{filename}' and '{FOLDER_ID}' in parents",
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None

def search_files(search_term):
    """Search for files in the shared drive folder that match the search term."""
    results = service.files().list(
        q=f"name contains '{search_term}' and '{FOLDER_ID}' in parents",
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = results.get("files", [])
    return files

def download_file(file_id):
    request = service.files().get_media(
        fileId=file_id,
        supportsAllDrives=True
    )
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# --- Streamlit UI ---
st.title("📸 Nepali Form C Photo Uploader")

st.subheader("Upload Photo")
name = st.text_input("Person's Name")
photo = st.file_uploader("Choose a photo", type=["jpg", "jpeg", "png"])

# Show image preview if photo is uploaded
if photo:
    st.image(photo, caption="Preview", width="stretch")

# Add upload button
if st.button("Upload Photo") and photo and name:
    safe_name = sanitize_filename(name)
    compressed = compress_image(photo)
    final_name = f"{safe_name}.jpg"

    if os.path.getsize(compressed) <= 50_000:
        fid = upload_to_drive(compressed, final_name)
        st.success(f"✅ Uploaded as {final_name}")
        st.caption(f"Drive file ID → {fid}")
        
        # Auto-download the compressed image
        with open(compressed, "rb") as f:
            st.download_button(
                label="⬇️ Download Compressed Image",
                data=f.read(),
                file_name=final_name,
                mime="image/jpeg"
            )
    else:
        st.error("❌ Could not compress below 50 KB. Try a smaller photo.")

st.divider()
st.subheader("Download Photo")
search_term = st.text_input("Search for files (e.g. John, Doe, etc.)")

if search_term:
    # Search for matching files
    matching_files = search_files(search_term)
    
    if matching_files:
        st.write(f"Found {len(matching_files)} file(s):")
        
        # Create a dropdown with file names
        file_names = [f["name"] for f in matching_files]
        selected_file = st.selectbox("Select a file to download:", file_names)
        
        # Find the selected file's ID
        selected_file_id = next(f["id"] for f in matching_files if f["name"] == selected_file)
        
        # Show preview of selected image
        fh = download_file(selected_file_id)
        st.image(fh, caption=f"Preview: {selected_file}", width="stretch")
        
        # Download button
        fh.seek(0)  # Reset file pointer for download
        st.download_button(
            label="⬇️ Download Selected File",
            data=fh,
            file_name=selected_file,
            mime="image/jpeg"
        )
    else:
        st.warning("❌ No files found matching your search.")
