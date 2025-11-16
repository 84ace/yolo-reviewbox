
from PIL import Image

# Create a 100x100 green image
img = Image.new('RGB', (100, 100), color = 'green')
img.save('image_catalog/test_image.png')
