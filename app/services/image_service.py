"""
app/services/image_service.py
Cloudinary integration for product image uploads.

Configured lazily on first actual use (not at import time) so the app can
still boot and every other Products feature works fine even before
Cloudinary credentials are added to .env.
"""

import cloudinary
import cloudinary.uploader
from flask import current_app

_configured = False


def _ensure_configured():
    global _configured
    if _configured:
        return
    cloudinary.config(
        cloud_name=current_app.config.get("CLOUDINARY_CLOUD_NAME"),
        api_key=current_app.config.get("CLOUDINARY_API_KEY"),
        api_secret=current_app.config.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )
    _configured = True


def upload_product_image(file, product_id: str) -> dict:
    """
    Uploads a single image file to Cloudinary under a per-product folder.
    Returns {"url": ..., "public_id": ...} — public_id is stored so the
    image can be deleted from Cloudinary later.

    `file` is a werkzeug FileStorage object from request.files.
    """
    _ensure_configured()

    result = cloudinary.uploader.upload(
        file,
        folder=f"iandg/products/{product_id}",
        resource_type="image",
        transformation=[{"quality": "auto", "fetch_format": "auto"}],
    )

    return {
        "url": result["secure_url"],
        "public_id": result["public_id"],
    }


def delete_product_image(public_id: str) -> bool:
    """Deletes an image from Cloudinary by its public_id. Returns True on success."""
    if not public_id:
        return False
    _ensure_configured()
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"
    except Exception:
        current_app.logger.warning(f"Failed to delete Cloudinary image: {public_id}")
        return False