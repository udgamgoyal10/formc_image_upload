# Secrets Configuration Template

## Local Development

For local development, create a file at `.streamlit/secrets.toml` with your credentials.

**IMPORTANT: Never commit this file to GitHub!**

## Streamlit Cloud Deployment

When deploying to Streamlit Cloud, add these sections to your app secrets in the Streamlit dashboard.

## Database Credentials

Add this section to your secrets:

```toml
[database]
host = "10.3.8.200"  # Your MySQL server hostname
port = 3306         # Your MySQL server port
user = "username"    # Your database username
password = "password" # Your database password
database = "form_c"  # Your database name
```

## Authentication Credentials

Add this section for basic authentication:

```toml
[auth]
username = "your_username"
password = "your_password"
```

## Complete Secrets File Structure

Your complete `.streamlit/secrets.toml` should have these sections:

1. **[auth]** - Basic authentication (username and password)
2. **[google_service_account]** - Google Drive API credentials
3. **[drive]** - Google Drive folder ID
4. **[database]** - MySQL database connection details

Make sure all sections are present when deploying to Streamlit Cloud!
