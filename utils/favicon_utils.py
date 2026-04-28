"""
Favicon Utility Module
Converts logo images (PNG, JPG, GIF, WebP) to ICO favicon format.
Uses Pillow library for image manipulation.
"""
import os
import logging
from typing import Optional, Tuple
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None

logger = logging.getLogger(__name__)


class FaviconUtils:
    """Utility class for favicon generation and conversion."""
    
    SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
    DEFAULT_FAVICON_SIZE = 64
    ICO_SIZES = [(16, 16), (32, 32), (64, 64), (128, 128)]
    
    @staticmethod
    def is_pil_available() -> bool:
        """Check if Pillow library is available."""
        return Image is not None
    
    @staticmethod
    def convert_logo_to_favicon(logo_path: str, output_path: str, size: int = 64) -> bool:
        """Convert a logo image file to ICO favicon.
        
        Args:
            logo_path: Path to source logo image file
            output_path: Path where favicon.ico will be saved
            size: Favicon size in pixels (default: 64)
            
        Returns:
            True if conversion successful, False otherwise
        """
        if not FaviconUtils.is_pil_available():
            logger.error("Pillow library not available. Cannot convert favicon.")
            return False
        
        if not os.path.exists(logo_path):
            logger.error(f"Logo file not found: {logo_path}")
            return False
        
        try:
            # Open and convert image
            img = Image.open(logo_path)
            
            # Convert RGBA to RGB if necessary for ICO format
            if img.mode == 'RGBA':
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize to square favicon size
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            
            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save as ICO with multiple sizes
            icon_sizes = [(16, 16), (32, 32), (64, 64)]
            icon_images = []
            
            for icon_size in icon_sizes:
                icon_img = img.resize(icon_size, Image.Resampling.LANCZOS)
                icon_images.append(icon_img)
            
            # Save ICO file
            img.save(output_path, format='ICO', sizes=[(s, s) for s in [16, 32, 64]])
            
            logger.info(f"Favicon successfully created: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting favicon: {e}")
            return False
    
    @staticmethod
    def generate_favicon_from_image_bytes(image_bytes: bytes, output_path: str, size: int = 64) -> bool:
        """Generate favicon from image bytes (uploaded file data).
        
        Args:
            image_bytes: Raw image file bytes
            output_path: Path where favicon.ico will be saved
            size: Favicon size in pixels (default: 64)
            
        Returns:
            True if conversion successful, False otherwise
        """
        if not FaviconUtils.is_pil_available():
            logger.error("Pillow library not available. Cannot convert favicon.")
            return False
        
        try:
            # Load image from bytes
            img = Image.open(BytesIO(image_bytes))
            
            # Convert RGBA to RGB if necessary
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize to square favicon size
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            
            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save as ICO with multiple sizes
            img.save(output_path, format='ICO', sizes=[(s, s) for s in [16, 32, 64]])
            
            logger.info(f"Favicon successfully created from bytes: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting favicon from bytes: {e}")
            return False
    
    @staticmethod
    def cleanup_old_favicon(favicon_path: str) -> bool:
        """Remove old favicon file before generating new one.
        
        Args:
            favicon_path: Path to favicon file to delete
            
        Returns:
            True if deleted or didn't exist, False if error occurred
        """
        try:
            if os.path.exists(favicon_path):
                os.remove(favicon_path)
                logger.info(f"Removed old favicon: {favicon_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting old favicon: {e}")
            return False
    
    @staticmethod
    def validate_image_file(file_path: str, max_size_mb: int = 5) -> Tuple[bool, str]:
        """Validate uploaded image file.
        
        Args:
            file_path: Path to image file to validate
            max_size_mb: Maximum file size in megabytes
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not os.path.exists(file_path):
            return False, "File not found"
        
        # Check file extension
        _, ext = os.path.splitext(file_path)
        if ext.lower() not in FaviconUtils.SUPPORTED_FORMATS:
            return False, f"Unsupported file format: {ext}. Supported: {FaviconUtils.SUPPORTED_FORMATS}"
        
        # Check file size
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > max_size_mb:
            return False, f"File size ({file_size_mb:.1f}MB) exceeds maximum ({max_size_mb}MB)"
        
        # Try to open and validate it's a valid image
        if not FaviconUtils.is_pil_available():
            return True, ""  # Can't validate without Pillow, but allow
        
        try:
            with Image.open(file_path) as img:
                img.verify()
            return True, ""
        except Exception as e:
            return False, f"Invalid image file: {e}"
    
    @staticmethod
    def get_image_dimensions(file_path: str) -> Optional[Tuple[int, int]]:
        """Get image dimensions (width, height).
        
        Args:
            file_path: Path to image file
            
        Returns:
            Tuple of (width, height) or None if error
        """
        if not FaviconUtils.is_pil_available():
            return None
        
        try:
            with Image.open(file_path) as img:
                return img.size
        except Exception as e:
            logger.error(f"Error getting image dimensions: {e}")
            return None
