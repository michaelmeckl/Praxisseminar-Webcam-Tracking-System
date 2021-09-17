import os
import pathlib
from post_processing.post_processing_constants import download_folder


RANDOM_SEED = 42
NUMBER_OF_CLASSES = 3
DEFAULT_TRAIN_SPLIT = 0.8  # take 80 % of the participants as train data per default
TRAIN_EPOCHS = 20

NEW_IMAGE_SIZE = (172, 172)

# for VGG16, Resnet50 and EfficientNetB0:
# NEW_IMAGE_SIZE = (224, 224)  # format: (height, width)
# for Inception_v3 and Xception:
# NEW_IMAGE_SIZE = (299, 299)

results_folder = "ml_results"
images_path = pathlib.Path(__file__).parent.parent / "post_processing"
data_folder_path = os.path.join(os.path.dirname(__file__), "..", "post_processing", download_folder)