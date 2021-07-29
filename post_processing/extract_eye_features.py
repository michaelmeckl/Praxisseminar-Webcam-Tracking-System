#!/usr/bin/python3
# -*- coding:utf-8 -*-

import argparse
import os
import sys
import time
import cv2
from datetime import datetime
from post_processing.eye_tracking.eye_tracker import EyeTracker
from post_processing.post_processing_constants import download_folder, image_folder


# TODO Lösungsansätze für Problem mit unterschiedlichen Bilddimensionen pro Frame:
# 1. kleinere bilder mit padding versehen bis alle gleich groß wie größtes
# 2. größere bilder runterskalieren bis alle gleich groß wie kleinstes (oder alternativ crop)
# 3. jetzt erstmal unterschiedlich lassen und dann später beim CNN vorverarbeiten!
#      -> vermtl. eh am besten weil später neue Bilder ja auch erstmal vorverarbeitet werden müssen!


def debug_postprocess(enable_annotation, show_video, video_file_path):
    # uses the webcam or a given video file for the processing & annotation instead of the images from the participants
    if args.video_file:
        # use a custom threaded video captures to increase fps;
        # see https://www.pyimagesearch.com/2015/12/21/increasing-webcam-fps-with-python-and-opencv/
        from post_processing.eye_tracking.ThreadedFileVideoCapture import FileVideoStream
        capture = FileVideoStream(path=video_file_path, transform=None)
    else:
        # fall back to webcam (0) if no input video was provided
        capture = cv2.VideoCapture(0)

    video_width, video_height = capture.get(3), capture.get(4)
    print(f"Capture Width: {video_width}, Capture Height: {video_height}")
    eye_tracker = EyeTracker(video_width, video_height, enable_annotation, show_video)

    c = 0
    start_time = datetime.now()
    while True:
        return_val, curr_frame = capture.read()
        if curr_frame is None:
            break
        c += 1

        processed_frame = eye_tracker.process_current_frame(curr_frame)

        # show fps in output image
        elapsed_time = (datetime.now() - start_time).total_seconds()
        fps = c / elapsed_time if elapsed_time != 0 else c
        cv2.putText(processed_frame, f"mainthread FPS: {fps:.3f}",
                    (350, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("fps_main_thread", processed_frame)

        # press q to quit this loop
        if cv2.waitKey(1) & 0xFF == ord('q'):
            cv2.destroyAllWindows()
            break


def process_images(eye_tracker):
    frame_count = 0
    start_time = time.time()
    for sub_folder in os.listdir(download_folder):
        # TODO or directly use the labeled images subfolder instead of image_folder here?
        images_path = os.path.join(download_folder, sub_folder, image_folder)
        for image_file in os.listdir(images_path):
            current_frame = cv2.imread(os.path.join(images_path, image_file))
            processed_frame = eye_tracker.process_current_frame(current_frame)

            frame_count += 1
            cv2.imshow("processed_frame", processed_frame)
            # press q to quit earlier
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    duration = time.time() - start_time
    print(f"[INFO]: Frame Count: {frame_count}")
    print(f"[INFO]: Duration: {duration} seconds")
    # print(f"[INFO]: FPS: {duration / frame_count:.3f}")

    # cleanup
    cv2.destroyAllWindows()
    sys.exit(0)


def start_extracting_features(debug=False, enable_annotation=False, show_video=True, video_file_path=None):
    if debug:
        debug_postprocess(enable_annotation, show_video, video_file_path)
    else:
        frame_width, frame_height = None, None

        # get size of first image; TODO dirty way for now, improve later
        for sub_folder in os.listdir(download_folder):
            for image in os.listdir(os.path.join(download_folder, sub_folder, image_folder)):
                # this is the first image
                first_image = cv2.imread(os.path.join(download_folder, sub_folder, image_folder, image))
                frame_width = first_image.shape[1]
                frame_height = first_image.shape[0]
                break  # we only want the first image, so we stop immediately

        if frame_width is None:
            print("first image doesn't seem to exist!")
            return

        # TODO resize all images to the same size for head pose estimator!! e.g. use keras.flow_from_directory ??
        eye_tracker = EyeTracker(frame_width, frame_height, enable_annotation, show_video)
        process_images(eye_tracker)


if __name__ == "__main__":
    # setup an argument parser to enable command line parameters
    parser = argparse.ArgumentParser(description="Postprocessing system to find the useful data in the recorded "
                                                 "images.")
    parser.add_argument("-v", "--video_file", help="path to a video file to be used instead of the webcam", type=str)
    parser.add_argument("-a", "--enable_annotation", help="If enabled the tracked face parts are highlighted in the "
                                                          "current frame", action="store_true")
    parser.add_argument("-s", "--show_video", help="If enabled the given video or the webcam recoding is shown in a "
                                                   "separate window", action="store_true")
    args = parser.parse_args()
    annotation_enabled = args.enable_annotation
    video_enabled = args.show_video
    video_file = args.video_file

    start_extracting_features(debug=False, enable_annotation=annotation_enabled, show_video=video_enabled,
                              video_file_path=video_file)