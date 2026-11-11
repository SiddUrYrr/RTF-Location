import os
import re
import logging
from typing import Optional, Dict, Any, Union
from dotenv import load_dotenv

logger = logging.getLogger("cloudinary_service")

def get_cloudinary_credentials():
    """
    Extracts Cloudinary credentials from environment.
    Supports either CLOUDINARY_URL or CLOUDINARY_CLOUD_NAME + CLOUDINARY_API_KEY + CLOUDINARY_API_SECRET.
    """
    load_dotenv(override=True)
    
    # 1. Check CLOUDINARY_URL (e.g. cloudinary://12345:abcdef@cloudname)
    cloudinary_url = os.getenv("CLOUDINARY_URL", "").strip()
    if cloudinary_url:
        match = re.match(r"^cloudinary:\/\/([^:]+):([^@]+)@([^\/\?]+)", cloudinary_url)
        if match:
            api_key, api_secret, cloud_name = match.groups()
            return cloud_name.strip(), api_key.strip(), api_secret.strip()

    # 2. Check individual environment variables
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()

    return cloud_name, api_key, api_secret

def init_cloudinary() -> bool:
    """
    Configures the Cloudinary SDK if credentials exist.
    """
    cloud_name, api_key, api_secret = get_cloudinary_credentials()
    if not cloud_name or not api_key or not api_secret:
        return False

    try:
        import cloudinary
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )
        return True
    except Exception as e:
        logger.warning("Could not initialize Cloudinary: %s", e)
        return False

def is_cloudinary_configured() -> bool:
    """
    Quick check if credentials are set in environment.
    """
    cloud_name, api_key, api_secret = get_cloudinary_credentials()
    return bool(cloud_name and api_key and api_secret)

def check_cloudinary_status() -> Dict[str, Any]:
    """
    Verifies Cloudinary configuration and makes a live ping to verify credentials.
    """
    cloud_name, api_key, api_secret = get_cloudinary_credentials()
    if not (cloud_name and api_key and api_secret):
        return {
            "configured": False,
            "connected": False,
            "cloud_name": cloud_name or None,
            "message": "Cloudinary credentials missing in .env (Add CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET or CLOUDINARY_URL)"
        }

    try:
        import cloudinary
        import cloudinary.api
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )
        res = cloudinary.api.ping()
        if res.get("status") == "ok":
            return {
                "configured": True,
                "connected": True,
                "cloud_name": cloud_name,
                "message": f"Cloudinary successfully connected to cloud: {cloud_name}"
            }
        else:
            return {
                "configured": True,
                "connected": False,
                "cloud_name": cloud_name,
                "message": f"Cloudinary responded with status: {res.get('status')}"
            }
    except Exception as e:
        error_msg = str(e)
        logger.error("Cloudinary ping failed: %s", error_msg)
        return {
            "configured": True,
            "connected": False,
            "cloud_name": cloud_name,
            "message": f"Cloudinary connection error: {error_msg}"
        }

def _save_avatar_locally(image_data: Union[str, bytes], user_id: int) -> str:
    """
    Saves image data locally to frontend/uploads/avatars/ and returns static URL.
    Ensures avatars work 100% reliably even if Cloudinary has restricted permissions.
    """
    try:
        from pathlib import Path
        import base64
        base_dir = Path(__file__).resolve().parent.parent
        upload_dir = base_dir / "frontend" / "uploads" / "avatars"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"user_{user_id}.jpg"

        if isinstance(image_data, bytes):
            with open(file_path, "wb") as f:
                f.write(image_data)
        elif isinstance(image_data, str) and image_data.startswith("data:image"):
            # Extract base64 payload
            if "," in image_data:
                _, b64_str = image_data.split(",", 1)
            else:
                b64_str = image_data
            img_bytes = base64.b64decode(b64_str)
            with open(file_path, "wb") as f:
                f.write(img_bytes)
        else:
            return image_data

        return f"/static/uploads/avatars/user_{user_id}.jpg"
    except Exception as e:
        logger.error("Failed to save avatar locally: %s", e)
        return image_data

def upload_avatar(image_data: Union[str, bytes], user_id: int) -> str:
    """
    Uploads user avatar to Cloudinary CDN and returns high-speed secure HTTPS URL.
    - If Cloudinary upload is successful, returns secure CDN URL.
    - If Cloudinary fails or has restricted permissions, returns persistent compressed base64
      data URL so the image is stored directly in database and NEVER deleted on code updates!
    - Also saves a local backup in frontend/uploads/avatars/.
    """
    if not image_data:
        return image_data

    # If it's already an external hosted URL, return as is
    if isinstance(image_data, str) and (image_data.startswith("http://") or image_data.startswith("https://")):
        return image_data

    if is_cloudinary_configured() and init_cloudinary():
        try:
            import cloudinary.uploader
            res = cloudinary.uploader.upload(
                image_data,
                public_id=f"user_{user_id}_avatar",
                folder="rtf-location/avatars",
                overwrite=True,
                invalidate=True,
                resource_type="image",
                transformation=[
                    {"width": 300, "height": 300, "crop": "fill", "gravity": "face"},
                    {"quality": "auto", "fetch_format": "auto"}
                ]
            )
            secure_url = res.get("secure_url")
            if secure_url:
                logger.info("Uploaded avatar to Cloudinary successfully: %s", secure_url)
                return secure_url
        except Exception as e:
            logger.warning("Cloudinary avatar upload rejected (%s); storing persistent image in database.", e)

    # Save local copy for offline static file serving
    _save_avatar_locally(image_data, user_id)

    # 100% Persistent Storage in DB Text column:
    # Storing the compressed base64 data URL directly ensures that ANY code update,
    # git push, git checkout, or container restart NEVER loses or wipes the user's profile image!
    if isinstance(image_data, str) and image_data.startswith("data:image"):
        return image_data

    if isinstance(image_data, bytes):
        import base64
        return f"data:image/jpeg;base64,{base64.b64encode(image_data).decode('utf-8')}"

    return _save_avatar_locally(image_data, user_id)
