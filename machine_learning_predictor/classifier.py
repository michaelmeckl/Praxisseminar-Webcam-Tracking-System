import os
import sys
import numpy as np
import psutil
import tensorflow as tf
from matplotlib import pyplot as plt
from tensorflow.keras.callbacks import ModelCheckpoint, ReduceLROnPlateau, LambdaCallback, EarlyStopping
from machine_learning_predictor.difficulty_levels import DifficultyLevels
from machine_learning_predictor.machine_learning_constants import results_folder, NEW_IMAGE_SIZE
from machine_learning_predictor.ml_utils import show_result_plot


# noinspection PyAttributeOutsideInit
class DifficultyImageClassifier:
    """
    Custom CNN for predicting the difficulty level with images of a user's face.
    """

    def __init__(self, train_generator, val_generator, num_classes, num_epochs=30):
        self.n_classes = num_classes
        self.n_epochs = num_epochs

        self.train_generator = train_generator
        self.validation_generator = val_generator

        # check the maximum number of available cores
        cpu_count_available = len(psutil.Process().cpu_affinity()),  # number of usable cpus by this process
        print("CPU Count available", cpu_count_available)
        self.num_workers = cpu_count_available[0] if cpu_count_available[0] else 1

    # TODO try VGG-16 and check if it changes something if a different architecture is used, see
    #  https://medium.com/deep-learning-with-keras/tf-data-build-efficient-tensorflow-input-pipelines-for-image-datasets-47010d2e4330

    # TODO: use keras.Tuner or Optuna for hyperparameter search!
    def build_model(self, input_shape: tuple) -> tf.keras.Model:
        self.sequential_model = tf.keras.Sequential(
            [
                tf.keras.layers.Conv2D(32, (3, 3), activation='relu', input_shape=input_shape),
                tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
                tf.keras.layers.Conv2D(64, (3, 3), activation='relu'),  # TODO use padding='same' ?
                tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
                tf.keras.layers.Conv2D(128, (3, 3), activation='relu'),
                tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),

                tf.keras.layers.Flatten(),
                # units in the last layer should be a power of two
                tf.keras.layers.Dense(units=256, activation="relu"),

                # tf.keras.layers.Dropout(0.3),
                # TODO add BatchNormalization() Layers instead of Dropout after every conv2d layer ?
                # tf.keras.layers.BatchNormalization(),

                # units must be the number of classes -> we want a vector that looks like this: [0.2, 0.5, 0.3]
                tf.keras.layers.Dense(units=self.n_classes, activation="softmax")
                # use softmax for multi-class classification, see
                # https://medium.com/deep-learning-with-keras/how-to-solve-classification-problems-in-deep-learning-with-tensorflow-keras-6e39c5b09501
            ]
        )

        self.sequential_model.summary()

        opt = tf.keras.optimizers.Adam(learning_rate=0.001, epsilon=0.1)  # epsilon default: 1e-07
        # for the choice of last layer, activation and loss functions see
        # https://medium.com/deep-learning-with-keras/which-activation-loss-functions-in-multi-class-clasification-4cd599e4e61f
        self.sequential_model.compile(optimizer=opt,
                                      loss="categorical_crossentropy",
                                      metrics=["categorical_accuracy"])

        # TODO use SparseCategoricalCrossentropy and accuracy as metrics?
        # self.sequential_model.compile(optimizer='adam', loss=tf.losses.SparseCategoricalCrossentropy(
        # from_logits=True), metrics=['accuracy'])

        tf.keras.utils.plot_model(self.sequential_model, "sequential_model_graph.png")
        return self.sequential_model

    def build_model_functional_version(self, input_shape: tuple) -> tf.keras.Model:
        inputs = tf.keras.Input(shape=input_shape)
        conv1 = tf.keras.layers.Conv2D(32, kernel_size=(3, 3), activation='relu')(inputs)
        pool1 = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(conv1)
        conv2 = tf.keras.layers.Conv2D(64, kernel_size=(3, 3), activation='relu')(pool1)
        pool2 = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(conv2)
        conv3 = tf.keras.layers.Conv2D(128, kernel_size=(3, 3), activation='relu')(pool2)
        pool3 = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(conv3)

        flatten = tf.keras.layers.Flatten()(pool3)
        dense1 = tf.keras.layers.Dense(512, activation='relu')(flatten)
        dropout = tf.keras.layers.Dropout(0.5)(dense1)
        # units must be the number of classes -> we want a vector that looks like this: [0.2, 0.5, 0.3]
        output = tf.keras.layers.Dense(self.n_classes, activation='softmax')(dropout)

        self.model = tf.keras.Model(inputs=inputs, outputs=output, name="functional_model_version")
        print(self.model.summary())

        tf.keras.utils.plot_model(self.model, to_file="functional_model_graph.png")  # needs graphviz and pydot to work!
        tf.keras.utils.plot_model(self.model, "functional_model_graph_with_shape_info.png", show_shapes=True)

        self.model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["categorical_accuracy"])
        return self.model

    def build_and_train_multi_input_model(self, train, val, sequence_length, input_shape: tuple):
        # Idea based on https://stackoverflow.com/questions/53020898/multiple-input-cnn-for-images
        branches = []
        for i in range(sequence_length):
            inputs = tf.keras.Input(shape=input_shape)
            conv1 = tf.keras.layers.Conv2D(32, kernel_size=(3, 3), activation='relu')(inputs)
            pool1 = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(conv1)
            conv2 = tf.keras.layers.Conv2D(64, kernel_size=(3, 3), activation='relu')(pool1)
            pool2 = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(conv2)
            flatten = tf.keras.layers.Flatten()(pool2)

            model = tf.keras.Model(inputs=inputs, outputs=flatten)
            branches.append(model)

        combinedInput = tf.keras.layers.concatenate([branch.output for branch in branches])

        dense1 = tf.keras.layers.Dense(128, activation='relu')(combinedInput)
        dropout = tf.keras.layers.Dropout(0.5)(dense1)
        # units must be the number of classes -> we want a vector that looks like this: [0.2, 0.5, 0.3]
        output = tf.keras.layers.Dense(self.n_classes, activation='softmax')(dropout)

        self.model = tf.keras.Model(inputs=[branch.input for branch in branches], outputs=output)
        # print(self.model.summary())
        # tf.keras.utils.plot_model(self.model, to_file="multi_input_model_graph.png")

        self.model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["categorical_accuracy"])

        all_train_batches = []
        all_train_labels = []
        all_val_labels = []
        all_val_batches = []

        # for i in range(train.n, 10):
        for i in range(10):
            batch_train, batch_train_labels = train[i]
            batch_val, batch_val_labels = val[i]

            all_train_batches.append(batch_train)
            all_val_batches.append(batch_val)
            all_train_labels.append(batch_train_labels)
            all_val_labels.append(batch_val_labels)

        self.model.fit(x=all_train_batches, y=all_train_labels, validation_data=(all_val_batches, all_val_labels),
                       use_multiprocessing=False,
                       # workers=self.num_workers,
                       epochs=self.n_epochs,
                       verbose=1)

    def log_custom_generator_info_before(self, batch, logs):
        print("\nBefore batch: ", batch, flush=True)
        print("Index list len:", len(self.train_generator.indices_list), flush=True)

    def log_custom_generator_info_after(self, batch, logs):
        print("\nAfter batch: ", batch, flush=True)
        print("Index list len:", len(self.train_generator.indices_list), flush=True)

    def train_classifier(self):
        self.step_size_train = self.train_generator.n // (self.train_generator.sequence_length *
                                                          self.train_generator.batch_size)
        self.step_size_val = self.validation_generator.n // (self.validation_generator.sequence_length *
                                                             self.validation_generator.batch_size)

        model_name = "Difficulty-CNN-Model-Generator.h5"
        model_path = os.path.join(results_folder, model_name)

        checkpoint_path = os.path.join(results_folder, "checkpoints_generator",
                                       "checkpoint-improvement-{epoch:02d}-{val_categorical_accuracy:.3f}.ckpt")
        # save checkpoints
        checkpoint_callback = ModelCheckpoint(checkpoint_path, monitor='val_categorical_accuracy', verbose=1,
                                              mode="max", save_best_only=True, save_weights_only=True)
        lr_callback = ReduceLROnPlateau(monitor='val_loss', factor=0.2, patience=5, verbose=1)

        # log_dir = "logs/" + datetime.now().strftime("%Y%m%d-%H%M%S")
        # tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=log_dir, histogram_freq=1, update_freq='batch')

        # define a custom callback
        custom_callback = LambdaCallback(
            on_batch_begin=self.log_custom_generator_info_before, on_batch_end=self.log_custom_generator_info_after)

        # TODO (val) loss on the first epoch should always be: -ln(1/n) with n = number_of_classes = 3
        #  -> 1.0986 here
        history = self.sequential_model.fit(self.train_generator,
                                            validation_data=self.validation_generator,
                                            shuffle=False,   # VERY IMPORTANT even when used with custom data
                                            # generator!
                                            # see https://github.com/keras-team/keras/issues/12082#issuecomment-455877627
                                            use_multiprocessing=False,
                                            workers=self.num_workers,
                                            epochs=self.n_epochs,
                                            callbacks=[checkpoint_callback, lr_callback],  # custom_callback],
                                            verbose=1)

        self.sequential_model.save(model_path)
        show_result_plot(history, self.n_epochs, metric="categorical_accuracy",
                         output_name="train_history_custom_generator.png")

        return history

    def train_classifier_dataset_version(self, train_ds, val_ds):
        model_name = "Difficulty-CNN-Model-Dataset.h5"
        model_path = os.path.join(results_folder, model_name)

        checkpoint_path = os.path.join(results_folder, "checkpoints_dataset",
                                       "checkpoint-improvement-{epoch:02d}-{val_categorical_accuracy:.3f}.ckpt")
        # save checkpoints
        checkpoint_callback = ModelCheckpoint(checkpoint_path, monitor='val_categorical_accuracy', verbose=1,
                                              mode="max", save_best_only=True, save_weights_only=True)
        lr_callback = ReduceLROnPlateau(monitor='val_loss', factor=0.2, patience=5, verbose=1)

        # early_callback = tf.keras.callbacks.EarlyStopping(monitor='val_categorical_accuracy', mode='max',
        #                                                  restore_best_weights=True, patience=5, verbose=1)

        custom_callback = LambdaCallback(
            on_batch_begin=self.log_custom_generator_info_before, on_batch_end=self.log_custom_generator_info_after)

        history = self.sequential_model.fit(train_ds,
                                            validation_data=val_ds,
                                            #shuffle=False,
                                            use_multiprocessing=False,
                                            workers=self.num_workers,
                                            epochs=self.n_epochs,
                                            callbacks=[checkpoint_callback, lr_callback],  # custom_callback],
                                            verbose=1)

        self.sequential_model.save(model_path)
        show_result_plot(history, self.n_epochs, metric="categorical_accuracy",
                         output_name="train_history_custom_dataset.png")

        return history

    def evaluate_classifier(self):
        val_loss, val_acc = self.sequential_model.evaluate(self.validation_generator,
                                                           steps=self.step_size_val,
                                                           verbose=1)
        print("Validation loss: ", val_loss)
        print("Validation accuracy: ", val_acc * 100)

    def evaluate_classifier_dataset_version(self, val_ds):
        val_loss, val_acc = self.sequential_model.evaluate(val_ds, verbose=1)
        print("Validation loss: ", val_loss)
        print("Validation accuracy: ", val_acc * 100)

    def predict_test_generator(self, test_gen):
        predictions = self.sequential_model.predict(test_gen)
        score = tf.nn.softmax(predictions[0])  # take the softmax over all predictions ([0] because it's nested)
        # print("Predictions:\n", predictions)
        print(f"Confidence: {100 * np.max(score):.2f} %")

        # evaluate on the test set as well
        test_loss, test_acc = self.sequential_model.evaluate(test_gen, verbose=1)
        print("Test accuracy: ", test_acc * 100)

        # load latest (i.e. the best) checkpoint
        loaded_model = self.load_saved_model(dataset_version=False)  # re-create the model first!
        checkpoint_folder = os.path.join(results_folder, "checkpoints_generator")  # "checkpoints_dataset"

        latest = tf.train.latest_checkpoint(checkpoint_folder)
        loaded_model.load_weights(latest)
        # and re-evaluate the model
        loss, acc = loaded_model.evaluate(test_gen, verbose=1)
        print(f"Accuracy with restored model weights: {100 * acc:5.2f}%")

    def load_saved_model(self, dataset_version=False):
        model_name = "Difficulty-CNN-Model-Dataset.h5" if dataset_version else "Difficulty-CNN-Model-Generator.h5"
        model_path = os.path.join(results_folder, model_name)

        if os.path.exists(model_path):
            loaded_model = tf.keras.models.load_model(model_path)
            print("Model successfully loaded")
            return loaded_model
        else:
            sys.stderr.write("No saved model found!")
            return None

    def save_prediction_as_image(self, batch, sequence_number, actual_label, predicted_label, use_dataset=False):
        sequence = batch[sequence_number]
        sequence_len = int(sequence.shape[1] / sequence.shape[0])   # calculate the sequence length based on the shape
        img_height, img_width = NEW_IMAGE_SIZE

        plt.figure(figsize=(10, 10))
        plt.grid(False)
        plt.xticks([])
        plt.yticks([])
        plt.imshow(sequence[:, 0:sequence_len * img_width, :])
        plt.ylabel(DifficultyLevels.get_label_for_encoding(actual_label))
        plt.title(f"Predicted label: {predicted_label}")

        # TODO currently only the last images are saved and overwrite the previous ones
        plt.savefig(os.path.join(results_folder,
                                 f"{'ds_' if use_dataset else 'gen_'}_prediction_result_{sequence_number}.png"))

    def get_label_name_for_index_pos(self, index_pos):
        mask_array = np.zeros(self.n_classes, dtype=int)  # creates this: [0 0 0]
        mask_array[index_pos] = 1  # if index_pos was 0: [1 0 0]
        return DifficultyLevels.get_label_for_encoding(mask_array)

    def predict(self, img_batch, correct_labels):
        predictions = self.sequential_model.predict(img_batch)

        for i, (prediction, correct_label) in enumerate(zip(predictions, correct_labels)):
            score = tf.nn.softmax(prediction)  # TODO use this or prediction?
            print(f"\nPrediction for sequence {i}: {prediction}\nScore: {score})")
            index = np.argmax(score)
            predicted_label = self.get_label_name_for_index_pos(index)
            print(f"Correct label is  \"{DifficultyLevels.get_label_for_encoding(correct_label)}\"")
            print(f"Predicted label was \"{predicted_label}\" with a confidence of {100 * score[index]:.2f} %")

            self.save_prediction_as_image(img_batch, i, correct_label, predicted_label, use_dataset=False)
