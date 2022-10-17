<h1 align='center'> ShowdownAI </h1>
<br>
This project runs a bot using machine learning models to play Pokémon Showdown Gen 
8 Random Battles. In this project, you can have the bot play on the ladder, play
challenge requests, gather replay data for training, and recompile the machine
learning models with new data.

### Installation
Start by cloning this repository using:<br><br>
`git clone https://github.com/nczimmerman00/ShowdownAI.git`

### Prerequisites
There are several required packages for these scripts to function properly. To install
these packages, open a terminal (such as command prompt) in the folder where you 
cloned this repository and enter the following command: 
<br><br>
`pip install -r requirements.txt`
<br><br>
Note that this project uses a forked version of the aiopokeapi package. The version
specified in the requirements.txt must be used, as currently using the official
version may cause the bot to crash during api lookups for certain moves such as 
'Draco Meteor'.

### Get Started
First, start by entering your account details that the bot will play on in
webInterface/.env. If you don't have a program to open the .env file, simply rename
the file to a .txt file and edit it, then rename it back to '.env'.
The account being used must be verified with an email address before the bot can use it.

#### Play Pokemon Showdown
To let the bot play on Pokémon Showdown, open a terminal in the folder where you cloned
this repository and enter the following command: 
<br><br>
`python main.py`
<br><br>
You will then be prompted to select which machine learning model to use and how the
bot will play. Results of the bot's play will be saved in the results.csv file inside
the simulation folder.

#### Get Additional Training Data
To gain additional training data for the machine learning models, open a terminal in
the webInterface folder of the project, and run the command:
<br><br>
`python training.py`
<br><br>
Training data will be taken from the most recent games played in the Gen 8 Random Battle
format

#### Retrain the Machine Learning Models
To retrain the machine learning models, open a terminal in the battle_ai folder of this
project and run the command:
<br><br>
`python ai.py`

## Important Note
While the bot is playing on Pokémon Showdown or gathering replay data, make sure to keep
your mouse off of the Chrome web browser being used. There are important html
elements which can only be accessed while hovering over another element (such as a 
pokemon). Failing to do so may result in the program crashing.