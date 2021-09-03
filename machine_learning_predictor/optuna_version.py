#!/usr/bin/python3
# -*- coding:utf-8 -*-

import os
import pathlib
import random
import joblib
import pandas as pd
import tensorflow as tf
from machine_learning_predictor.custom_data_generator_v2 import CustomImageDataGenerator
from machine_learning_predictor.machine_learning_constants import NUMBER_OF_CLASSES, data_folder_path
from post_processing.post_processing_constants import download_folder
import optuna


def merge_participant_image_logs(participant_list):
    image_data_frame = pd.DataFrame()
    post_processing_folder_path = pathlib.Path(__file__).parent.parent / "post_processing"

    for participant in participant_list:
        images_label_log = post_processing_folder_path / download_folder / participant / "labeled_images.csv"
        # images_label_log = post_processing_folder_path / download_folder / participant / "labeled_eye_regions.csv"
        labeled_images_df = pd.read_csv(images_label_log)

        difficulty_level_df = pd.DataFrame()
        # TODO for testing take only the first 150 rows for each difficulty level
        for difficulty_level in labeled_images_df.difficulty.unique():
            # create a subset of the df that contains only the rows with this difficulty level
            sub_df = labeled_images_df[labeled_images_df.difficulty == difficulty_level]
            sub_df = sub_df[:150]
            difficulty_level_df = pd.concat([difficulty_level_df, sub_df])

        image_data_frame = pd.concat([image_data_frame, difficulty_level_df])

    # reset the df index as the concatenate above creates duplicate indexes
    image_data_frame_numbered = image_data_frame.reset_index(drop=True)
    # image_data_frame_numbered["index"] = image_data_frame_numbered.index  # add the index numbers as own column

    return image_data_frame_numbered


def get_suitable_sample_size(category_size):
    # use a divisor of the amount of images per difficulty category for a participant
    # -> this way their won't be any overlap of label categories or participants per sample!
    sample_size = 1
    for i in range(10, 101):
        if category_size % i == 0:
            sample_size = i
            break

    """
    # fps = get_smallest_fps()  # TODO
    fps = 14.3

    sample_time_span = 6  # 6 seconds as in the Fridman Paper: "Cognitive Load Estimation in the Wild"
    sample_size = round(fps * sample_time_span)  # the number of images we take as one sample
    """
    print("Sample size: ", sample_size)
    return sample_size


def split_train_test(participant_list, train_ratio=0.8):
    random.shuffle(participant_list)

    train_split = int(len(participant_list) * train_ratio)
    train_participants = participant_list[:train_split]
    test_participants = participant_list[train_split:]
    print(f"{len(train_participants)} participants used for training: {train_participants}")
    print(f"{len(test_participants)} participants used for validation: {test_participants}")

    return train_participants, test_participants


def create_optimizer(trial):
    # We optimize the choice of optimizers as well as their parameters.
    adam_lr = trial.suggest_float("adam_lr", 1e-5, 1e-1, log=True)
    return tf.keras.optimizers.Adam(learning_rate=adam_lr)


def create_classifier(trial):
    without_participants = []
    all_participants = os.listdir(data_folder_path)[:12]
    all_participants = [p for p in all_participants if p not in set(without_participants)]

    train_participants, test_participants = split_train_test(all_participants)
    train_data = merge_participant_image_logs(train_participants)
    val_data = merge_participant_image_logs(test_participants)

    # See https://stats.stackexchange.com/questions/153531/what-is-batch-size-in-neural-network for consequences of
    # the batch size. Smaller batches lead to better results in general. Batch sizes are usually a power of two.
    batch_size = trial.suggest_int("batch_size", 3, 4)
    train_epochs = 15  # TODO
    sample_size = trial.suggest_int("sample_size", 10, 20)
    print(f"Sample size: {sample_size} (Train data len: {len(train_data)}, val data len: {len(val_data)})")

    images_path = pathlib.Path(__file__).parent.parent / "post_processing"
    use_gray = False
    train_generator = CustomImageDataGenerator(data_frame=train_data, x_col_name="image_path", y_col_name="difficulty",
                                               sequence_length=sample_size, batch_size=batch_size,
                                               images_base_path=images_path, use_grayscale=use_gray, is_train_set=True)

    val_generator = CustomImageDataGenerator(data_frame=val_data, x_col_name="image_path", y_col_name="difficulty",
                                             sequence_length=sample_size, batch_size=batch_size,
                                             images_base_path=images_path, use_grayscale=use_gray, is_train_set=False)

    image_shape = train_generator.get_image_shape()
    print("Image Shape: ", image_shape)

    n_layers = trial.suggest_int("n_layers", 1, 3)

    model = tf.keras.Sequential()
    model.add(tf.keras.layers.InputLayer(input_shape=image_shape))

    for i in range(n_layers):
        model.add(
            tf.keras.layers.Conv2D(
                activation='relu',
                # use 'i' as the names should be unique!
                filters=trial.suggest_categorical(f"filters-{i}", [32, 64, 128, 256]),
                kernel_size=trial.suggest_categorical(f"kernel_size-{i}", [3, 5]),
                padding=trial.suggest_categorical(f"padding-{i}", ["valid", "same"])
            )
        )
        model.add(
            tf.keras.layers.MaxPooling2D(
                pool_size=trial.suggest_int(f"pool_size-{i}", 2, 3)
            )
        )

    model.add(tf.keras.layers.Flatten())
    # num_hidden = trial.suggest_categorical("units", [32, 64, 128, 512])
    num_hidden = int(trial.suggest_loguniform("units", 4, 128))
    model.add(tf.keras.layers.Dense(num_hidden, activation='relu'))
    model.add(tf.keras.layers.Dense(NUMBER_OF_CLASSES, activation='softmax'))

    print(model.summary())

    optimizer = create_optimizer(trial)
    metric = trial.suggest_categorical("metrics", ['categorical_accuracy', 'accuracy'])  # TODO
    model.compile(optimizer=optimizer, loss='categorical_crossentropy', metrics=metric)

    history = model.fit(train_generator,
                        validation_data=val_generator,
                        epochs=train_epochs,
                        # shuffle=False,
                        workers=8,
                        verbose=1)  # False)

    # Evaluate the model accuracy on the validation set.
    score = model.evaluate(val_generator, verbose=0)
    return score[1]


def objective(trial):
    from tensorflow.keras.backend import clear_session
    clear_session()

    joblib.dump(study, 'study.pkl')

    # set_random_seed()  # set seed for reproducibility  # TODO seed useful?
    acc_score = create_classifier(trial)
    print("\nacc score: ", acc_score)
    return acc_score


if __name__ == "__main__":
    # os.environ['CUDA_VISIBLE_DEVICES'] = '-1'  # use cpu instead of gpu

    gpus = tf.config.list_physical_devices('GPU')
    for gpu in gpus:
        print("Name:", gpu.name, "  Type:", gpu.device_type)
    if len(gpus) == 0:
        print("No gpu found!")
    else:
        tf.config.experimental.set_memory_growth(gpus[0], True)

    # sampler = TPESampler(seed=10)  # Make the sampler behave in a deterministic way.
    # study = optuna.create_study(sampler=sampler)

    if os.path.isfile('study.pkl'):
        study = joblib.load('study.pkl')
    else:
        study = optuna.create_study(direction="maximize")

    # study.optimize(objective, n_trials=25, timeout=2500, gc_after_trial=True)
    study.optimize(objective, n_trials=25, gc_after_trial=True)

    print("Number of finished trials: ", len(study.trials))

    print("Best trial:")
    trial = study.best_trial

    trial_df = study.trials_dataframe()
    print(trial_df.head(12))

    print("  Value: ", trial.value)

    print("  Params: ")
    for key, value in trial.params.items():
        print("    {}: {}".format(key, value))

    print(f"Best params:\n{study.best_params}")