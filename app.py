import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2 import service_account
from PIL import Image
import io, os, re
import pymysql
import pandas as pd

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
    
    # Try to get database credentials from secrets
    try:
        DB_CONFIG = {
            "host": st.secrets["database"]["host"],
            "port": int(st.secrets["database"]["port"]),
            "user": st.secrets["database"]["user"],
            "password": st.secrets["database"]["password"],
            "database": st.secrets["database"]["database"]
        }
        print("\n✅ Database credentials loaded from secrets.")
    except Exception as e:
        print(f"\n⚠️ Could not load database credentials: {str(e)}")
        print("Database search functionality will be limited.")

except:
    # Local testing with credentials.json
    print("\n⚠️ Using local credentials.json file.")
    SERVICE_ACCOUNT_FILE = "credentials.json"
    FOLDER_ID = "0AGhLT2zlih_HUk9PVA"
    
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    
    # For local testing, use a local secrets.toml file or environment variables
    # This is safer than hardcoding credentials
    DB_CONFIG = {
        "host": st.secrets["database"]["host"],
        "port": st.secrets["database"]["port"],
        "user": st.secrets["database"]["user"],
        "password": st.secrets["database"]["password"],
        "database": st.secrets["database"]["database"]
    }
    
    # Print instructions for local setup
    print("\n⚠️ Using placeholder database credentials.")
    print("To use real credentials locally, create a .streamlit/secrets.toml file.")
    print("See SECRETS_TEMPLATE.md for instructions.\n")

service = build("drive", "v3", credentials=creds)

# --- Utility functions ---
def sanitize_filename(name: str) -> str:
    """Remove spaces & special chars."""
    return re.sub(r"[^A-Za-z0-9_-]", "", name.replace(" ", "_"))

def encrypt_pp_number(original_pp: str) -> str:
    """
    Encrypts the PP number using the same logic as VBA Get_Reversed_PP_Number.
    Takes: FirstTwo + StrippedStr + LastTwo
    Returns: LastTwo + StrippedStr + FirstTwo
    """
    if not original_pp or len(original_pp) < 4:
        return original_pp  # Return as is if too short
        
    # Extract parts from original
    first_two = original_pp[:2]  # First two characters
    last_two = original_pp[-2:]  # Last two characters
    middle = original_pp[2:-2]  # Middle part
    
    # Encrypt: swap first and last
    encrypted_pp = last_two + middle + first_two
    
    return encrypted_pp

def decrypt_pp_number(encrypted_pp: str) -> str:
    """
    Reverses the PP number encryption.
    Original encryption: Result = LastTwo + StrippedStr + FirstTwo
    Decryption: Result = FirstTwo + StrippedStr + LastTwo
    """
    if not encrypted_pp or len(encrypted_pp) < 4:
        return encrypted_pp  # Return as is if too short
        
    # Extract parts
    last_two = encrypted_pp[:2]  # First two chars in encrypted are actually last two
    first_two = encrypted_pp[-2:]  # Last two chars in encrypted are actually first two
    middle = encrypted_pp[2:-2]  # Middle part stays the same
    
    # Reconstruct original PP number
    original_pp = first_two + middle + last_two
    
    return original_pp

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

# --- Database functions ---
@st.cache_resource(ttl=300)  # Cache for 5 minutes only
def get_db_connection():
    """Create and return a database connection."""
    try:
        # Print connection details for debugging (without password)
        debug_config = DB_CONFIG.copy()
        debug_config["password"] = "*****"
        print(f"Attempting to connect to database with: {debug_config}")
        
        # Set a shorter timeout for connection attempts (5 seconds for cloud)
        conn = pymysql.connect(**DB_CONFIG, connect_timeout=5)
        
        # Test the connection with a simple query
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            print(f"Database connection test result: {result}")
        
        return conn
    except pymysql.err.OperationalError as e:
        error_code = e.args[0] if e.args else 0
        if error_code == 2003:
            print(f"Database server unreachable: {str(e)}")
            print("This is expected on Streamlit Cloud if using a private IP address.")
        raise
    except Exception as e:
        print(f"Database connection error: {type(e).__name__}: {str(e)}")
        raise

def search_devotees(search_term):
    """Search devotees by First Name, Last Name, or PP Number."""
    try:
        # Check if we're using placeholder credentials
        if DB_CONFIG.get("user") == "user" and DB_CONFIG.get("password") == "password":
            st.error("⚠️ Database credentials not configured.")
            st.info("To use the database search feature:")
            st.info("1. Create a .streamlit/secrets.toml file with your database credentials")
            st.info("2. Or deploy to Streamlit Cloud and add credentials in the dashboard")
            st.info("See SECRETS_TEMPLATE.md for instructions")
            return None
        
        try:    
            # Try to get a connection
            conn = get_db_connection()
            
            # Create a cursor and execute the query
            cursor = conn.cursor()
            
            # We need to modify our approach since we can't decrypt in SQL
            # First, get all potential matches by first name or last name
            query = """
                SELECT ID, First_Name, Last_Name, PP_Number 
                FROM devotee 
                WHERE First_Name LIKE %s 
                   OR Last_Name LIKE %s 
                ORDER BY Last_Name, First_Name
            """
            
            # Log the query (without values for security)
            print(f"Executing query: {query.strip()}")
            
            search_pattern = f"%{search_term}%"
            print(f"Search pattern: '{search_pattern}'")
            
            # Execute the query with only first and last name parameters
            cursor.execute(query, (search_pattern, search_pattern))
            
            # Fetch all results and convert to list
            initial_results = list(cursor.fetchall())
            print(f"Initial query returned {len(initial_results) if initial_results else 0} results")
            
            # Close cursor
            cursor.close()
            
            # Check if this might be a PP number search
            if search_term.isdigit() or (len(search_term) >= 2 and any(c.isdigit() for c in search_term)):
                # Encrypt the search term to search the database
                encrypted_search_term = encrypt_pp_number(search_term)
                print(f"Encrypted search term: {encrypted_search_term}")
                
                # Search for the encrypted PP number in the database
                pp_query = """
                    SELECT ID, First_Name, Last_Name, PP_Number 
                    FROM devotee 
                    WHERE PP_Number LIKE %s
                    ORDER BY Last_Name, First_Name
                """
                
                cursor = conn.cursor()
                encrypted_pattern = f"%{encrypted_search_term}%"
                cursor.execute(pp_query, (encrypted_pattern,))
                pp_results = cursor.fetchall()
                cursor.close()
                
                print(f"PP number search returned {len(pp_results) if pp_results else 0} results")
                
                # Combine with name search results, avoiding duplicates
                seen_ids = set(r[0] for r in initial_results)
                for result in pp_results:
                    if result[0] not in seen_ids:
                        initial_results.append(result)
                        seen_ids.add(result[0])
                
                results = initial_results
                print(f"Total results after combining: {len(results)} results")
            else:
                # Not a PP number search, use initial results
                results = initial_results
            
        except pymysql.err.OperationalError as e:
            # Handle specific database operational errors
            error_code, error_message = e.args
            if error_code == 2003:
                st.error("🔌 Cannot connect to database server")
                st.warning("The database server is not accessible from this location.")
                st.info("**Note:** The database at 10.3.8.200 is on a private network and cannot be reached from Streamlit Cloud.")
                st.info("**Solutions:**")
                st.info("• Use a cloud-hosted MySQL service (AWS RDS, Google Cloud SQL, etc.)")
                st.info("• Set up a publicly accessible database server")
                st.info("• The database search feature works when running locally")
            else:
                st.error(f"Database connection error: {error_code} - {error_message}")
                st.info("The database server may be down or unreachable. Please try again later.")
            print(f"MySQL Operational Error: {error_code} - {error_message}")
            return None
            
        except Exception as e:
            # Handle other database errors
            st.error(f"Database error: {type(e).__name__} - {str(e)}")
            print(f"Unexpected database error: {type(e).__name__} - {str(e)}")
            return None
        
        # Convert to DataFrame
        if results:
            df = pd.DataFrame(results, columns=["Database ID", "First Name", "Last Name", "PP Number"])
            
            # Convert PP_Number column to string to prevent scientific notation
            df["PP Number"] = df["PP Number"].astype(str)
            
            # Decrypt the PP numbers
            df["PP Number"] = df["PP Number"].apply(decrypt_pp_number)
            
            # Rename PP Number to ID Number
            df = df.rename(columns={"PP Number": "ID Number"})
            
            return df
        else:
            return pd.DataFrame(columns=["Database ID", "First Name", "Last Name", "ID Number"])
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        st.info("If you're seeing connection errors, check your database credentials.")
        return None

# --- Streamlit UI ---
st.title("📸 Nepali Form C Photo Uploader")

# Create tabs
tab1, tab2 = st.tabs(["📤 Photo Management", "🔍 Database Search"])

# Tab 1: Photo Upload/Download
with tab1:
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

# Tab 2: Database Search
with tab2:
    st.subheader("Search Devotees Database")
    st.write("Search by First Name, Last Name, or PP Number")
    
    db_search_term = st.text_input("Enter search term:", key="db_search")
    
    if db_search_term:
        with st.spinner("Searching database..."):
            results_df = search_devotees(db_search_term)
        
        if results_df is not None:
            if not results_df.empty:
                st.success(f"Found {len(results_df)} result(s)")
                
                # Display results in a table
                st.dataframe(
                    results_df,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning(f"No results found for '{db_search_term}'")
                st.info("Try a different search term or check your spelling.")
                st.info("You can search by First Name, Last Name, or PP Number.")
                st.info("Partial matches are supported (e.g., 'Jo' will find 'John').")
        
    else:
        st.info("👆 Enter a search term above to search the database")
