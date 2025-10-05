# Form C Photo Uploader

A Streamlit application for uploading and downloading photos to/from Google Drive with automatic compression.

## Features

- 📤 Upload photos with automatic compression to under 50KB
- 🔍 Search and download photos from Google Drive
- 👁️ Preview images before downloading
- 🔒 Secure authentication via Google Service Account

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Add your `credentials.json` file (Google Service Account key) to the project root

3. Run the app:
```bash
streamlit run app.py
```

## Deployment to Streamlit Cloud

### Step 1: Prepare Your Repository

1. Push your code to GitHub (make sure `credentials.json` is in `.gitignore`)
2. Do NOT commit `credentials.json` or `.streamlit/secrets.toml`

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Select your repository and branch
4. Set main file path to `app.py`

### Step 3: Add Secrets

1. In your Streamlit Cloud dashboard, go to your app settings
2. Click on "Secrets" in the left sidebar
3. Copy the contents of `.streamlit/secrets.toml` and paste it into the secrets editor
4. Click "Save"

Your app will automatically restart and use the secrets for authentication!

## Google Drive Setup

1. Create a Google Service Account
2. Download the JSON key file
3. Create a folder in Google Drive (or use a Shared Drive)
4. Share the folder with your service account email (found in the JSON as `client_email`)
5. Give it "Editor" permissions
6. Copy the folder ID from the URL and update it in your secrets

## Environment Variables

The app automatically detects whether it's running locally or on Streamlit Cloud:
- **Local**: Uses `credentials.json` file
- **Streamlit Cloud**: Uses secrets from `.streamlit/secrets.toml`
