import keras.metrics
import os
import numpy as np
import pandas as pd
from keras import Sequential, callbacks
from keras.layers import Dense
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.metrics import accuracy_score
from pickle import dump


def append_status_column(df, column_name):
    statuses = ['BRN', 'PSN', 'TOX', 'FRZ', 'SLP', 'PAR']
    for status in statuses:
        column_check = column_name + '_' + status
        if column_check not in df:
            df[column_check] = 0


def append_type_column(df, column_name):
    types = ['None', 'Normal', 'Fire', 'Water', 'Grass', 'Electric', 'Ice', 'Fighting', 'Poison', 'Ground', 'Flying',
             'Psychic', 'Bug', 'Rock', 'Ghost', 'Dragon', 'Dark', 'Steel', 'Fairy']
    if 'Type1' in column_name:
        types.remove('None')
    for type in types:
        column_check = column_name + '_' + type
        if column_check not in df:
            df[column_check] = 0


def append_weather_column(df, column_name):
    weathers = ['Sun', 'Rain', 'Hail', 'Sandstorm', 'None']
    for weather in weathers:
        column_check = column_name + '_' + weather
        if column_check not in df:
            df[column_check] = 0


def append_terrain_column(df, column_name):
    terrains = ['Electric Terrain', 'Grassy Terrain', 'Psychic Terrain', 'Misty Terrain', 'None']
    for terrain in terrains:
        column_check = column_name + '_' + terrain
        if column_check not in df:
            df[column_check] = 0


if not os.path.isdir('models/'):
    os.mkdir('models')

### This code properly formats the data to be fed to the AI model ###

# Convert Binary Result Columns
df = pd.read_csv('training_data.csv', dtype={'P2LeadStatus': 'str'})
df = df.drop('Match_ID', axis=1)

df_binary = pd.get_dummies(df['WinOrLoss'])
df_combined = pd.concat((df_binary, df), axis=1)
df_combined = df_combined.drop(['WinOrLoss'], axis=1)
df_combined = df_combined.drop(['Loss'], axis=1)
df_combined = df_combined.rename(columns={"Win": "WinOrLoss"})
df = df_combined

binary_columns = ['P1ScreenUp', 'P2ScreenUp', 'P1HasDamageEntryHazards', 'P2HasDamageEntryHazards',
                  'P1HasToxicSpikes', 'P2HasToxicSpikes', 'P1HasStickyWeb', 'P2HasStickyWeb', 'P1DynamaxAvailable',
                  'P2DynamaxAvailable', 'P1LeadDynamaxed', 'P1LeadConfused', 'P1LeadLeechSeed', 'P1LeadDrowsy',
                  'P1LeadTaunted', 'P1LeadEncore', 'P1R1Revealed', 'P1R2Revealed', 'P1R3Revealed', 'P1R4Revealed',
                  'P1R5Revealed', 'P2LeadDynamaxed', 'P2LeadConfused', 'P2LeadLeechSeed', 'P2LeadDrowsy',
                  'P2LeadTaunted', 'P2LeadEncore', 'P2R1Revealed', 'P2R2Revealed', 'P2R3Revealed', 'P2R4Revealed',
                  'P2R5Revealed']
for column in binary_columns:
    df_binary = pd.get_dummies(data=df, columns=[column])
    df_combined = df_binary
    df_combined = df_combined.drop((column + '_False'), axis=1)
    df_combined = df_combined.rename(columns={(column + '_True'): column})
    df = df_combined

# Convert Categorical columns using One Hot Encoding
categorical_columns = ['Weather', 'Terrain', 'P1LeadType1', 'P1LeadType2', 'P1LeadStatus', 'P2LeadType1',
                       'P2LeadType2', 'P2LeadStatus']
df = pd.get_dummies(data=df, columns=categorical_columns)

# Add missing columns if necessary
status_columns = ['P1LeadStatus', 'P2LeadStatus']
type_columns = ['P1LeadType1', 'P1LeadType2', 'P2LeadType1', 'P2LeadType2']
for column in status_columns:
    append_status_column(df, column)
for column in type_columns:
    append_type_column(df, column)
append_terrain_column(df, 'Terrain')
append_weather_column(df, 'Weather')

# Sort the array
df = df.sort_index(axis=1)
# Grab dataset
df = df.to_numpy()
x = df[:, :-1]
min_max_scaler = MinMaxScaler()
x = min_max_scaler.fit_transform(x)
# Save the scalar
dump(min_max_scaler, open('models/scalar.pkl', 'wb'))
y = df[:, -1]
x = np.asarray(x).astype('float32')
x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.25, random_state=23, shuffle=True)
earlystopping = callbacks.EarlyStopping(monitor ="val_loss",
                                        mode ="min", patience = 5,
                                        restore_best_weights = True)

model1 = Sequential()
model1.add(Dense(64, input_shape=(157,), activation='relu'))
model1.add(Dense(32, activation='relu'))
model1.add(Dense(1, activation='sigmoid'))
model1.compile(loss='binary_crossentropy', optimizer='adam', metrics=[keras.metrics.BinaryAccuracy()])
model1.fit(x_train, y_train, epochs=50, batch_size=10, validation_data=(x_test, y_test), callbacks=[earlystopping])
_, accuracy = model1.evaluate(x, y)
model1.save('models/model1.h5')
print('Model 1 Accuracy: ' + str(accuracy*100) + '%')

model2 = Sequential()
model2.add(Dense(64, input_shape=(157,), activation='relu'))
model2.add(Dense(48, activation='relu'))
model2.add(Dense(32, activation='relu'))
model2.add(Dense(1, activation='sigmoid'))
model1.compile(loss='binary_crossentropy', optimizer='adam', metrics=[keras.metrics.BinaryAccuracy()])
model1.fit(x_train, y_train, epochs=50, batch_size=10, validation_data=(x_test, y_test), callbacks=[earlystopping])
_, accuracy = model1.evaluate(x, y)
model1.save('models/model2.h5')
print('Model 2 Accuracy: ' + str(accuracy*100) + '%')


model3 = LogisticRegression()
model3.fit(x_train, y_train)
predictions = model3.predict(x_test)
accuracy = accuracy_score(predictions, y_test)
print('Model 3 Accuracy: ' + str(accuracy))
pkl_filename = "models/model3.pkl"
with open(pkl_filename, 'wb') as file:
    dump(model3, file)

model4 = GaussianNB()
model4.fit(x_train, y_train)
predictions = model4.predict(x_test)
accuracy = accuracy_score(predictions, y_test)
print('Model 4 Accuracy: ' + str(accuracy))
test = model4.predict_proba(x_test[2].reshape(1, -1))
pkl_filename = 'models/model4.pkl'
with open(pkl_filename, 'wb') as file:
    dump(model4, file)
