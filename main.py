import tensorflow as tf
from keras.models import load_model


model =load_model('keras_model.h5')

con = tf.lite.TFLiteConverter.from_keras_model(model)
tflite_model = con.convert()

with open('model.tflite', 'wb') as f:
    f.write(tflite_model)
    