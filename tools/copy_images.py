import os
import shutil

labels_train_dir = './dataset/labels/train'
images_rat_dir = './rat'
images_possum_dir = './possum'
images_kea_dir = './kea'
images_kaka_dir = './kaka'
images_train_dir = './dataset/images/train'

# Bird folder (inside images/train)
images_bird_dir = os.path.join(images_train_dir, 'bird')

# Make sure destination directories exist
os.makedirs(images_train_dir, exist_ok=True)
os.makedirs(images_bird_dir, exist_ok=True)

# Get all base filenames from labels/train (without .txt)
label_files = [f[:-4] for f in os.listdir(labels_train_dir) if f.endswith('.txt')]

for base_name in label_files:
    found = False

    # Check in rat folder
    rat_path = os.path.join(images_rat_dir, base_name + '.png')
    if os.path.isfile(rat_path):
        shutil.copy(rat_path, images_train_dir)
        found = True
    else:
        # Check in possum folder
        possum_path = os.path.join(images_possum_dir, base_name + '.png')
        if os.path.isfile(possum_path):
            shutil.copy(possum_path, images_train_dir)
            found = True
        else:
            # Check in kea folder (copy to bird/)
            kea_path = os.path.join(images_kea_dir, base_name + '.png')
            if os.path.isfile(kea_path):
                shutil.copy(kea_path, images_bird_dir)
                found = True
            else:
                # Check in kaka folder (copy to bird/)
                kaka_path = os.path.join(images_kaka_dir, base_name + '.png')
                if os.path.isfile(kaka_path):
                    shutil.copy(kaka_path, images_bird_dir)
                    found = True

    if not found:
        print(f"Warning: No image found for label {base_name}")

print("Copying complete.")
